import asyncio
import contextlib
import itertools
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import certifi
import nats.errors as nats_errors
import pytest
from PasarGuardNodeBridge import Health, InMemoryUserSyncStore, NodeAPIError, NodeType
from PasarGuardNodeBridge.common.service_pb2 import Empty, User
from PasarGuardNodeBridge.grpclib import Node as GrpcNode
from PasarGuardNodeBridge.rest import Node as RestNode

from app.nats.kv_cas import MemoryCasKv, kv_get_json
from app.node import NodeManager, bridge as bridge_module
from app.node.bridge import create_node, register_refresh_handler
from app.node.nats_memory import NatsUserSyncStore


def make_node(transport, store=None, **kwargs):
    kwargs.setdefault("node_id", uuid4().hex)
    node = create_node(
        connection=NodeType(transport),
        address="localhost",
        port=1,
        api_port=1,
        server_ca=certifi.contents(),
        api_key=str(uuid4()),
        user_sync_store=store if store is not None else InMemoryUserSyncStore(),
        **kwargs,
    )
    node._sync_poll_interval = 0.005
    node._worker_idle_timeout = 0.05
    return node


async def close_node(node):
    await node.disconnect()
    if hasattr(node, "channel"):
        node.channel.close()
    await node._json_client.close()


class FakeNodeState:
    """Records what a node would hold: full snapshots replace, deltas merge."""

    def __init__(self):
        self.users: dict[str, list[str]] = {}
        self.deltas: list[list[str]] = []
        self.snapshots: list[list[str]] = []
        self.gate: asyncio.Event | None = None
        self.delta_started = asyncio.Event()

    async def apply_delta(self, users):
        self.delta_started.set()
        if self.gate is not None:
            await self.gate.wait()
        for user in users:
            self.users[user.email] = list(user.inbounds)
        self.deltas.append([user.email for user in users])
        return []

    async def apply_snapshot(self, users):
        self.users = {user.email: list(user.inbounds) for user in users}
        self.snapshots.append([user.email for user in users])
        return Empty()


def attach_fake_transport(monkeypatch, node, state: FakeNodeState):
    """Replace the bridge transport underneath the adapter, keeping its locking shape.

    Patched at the base classes so the adapter's own overrides (delivery
    deadline, fence checks) stay in the call chain exactly as in production.
    """
    node._fake_state = state

    def fake(name, with_lock):
        originals = {cls: getattr(cls, name) for cls in (GrpcNode, RestNode)}

        async def method(self, *args, **kwargs):
            fake_state = getattr(self, "_fake_state", None)
            if fake_state is None:
                return await originals[type(self).__mro__[-3]](self, *args, **kwargs)
            if name == "sync_users":
                users = args[0] if args else kwargs["users"]
                if args[1] if len(args) > 1 else kwargs.get("flush_pending"):
                    await self.flush_pending_users()
                async with self._node_lock:
                    return await fake_state.apply_snapshot(users)
            users = args[0] if args else kwargs["users"]
            if with_lock:
                async with self._node_lock:
                    return await fake_state.apply_delta(users)
            return await fake_state.apply_delta(users)

        for cls in originals:
            monkeypatch.setattr(cls, name, method)

    fake("sync_users_chunked", with_lock=True)
    fake("sync_users", with_lock=True)
    fake("_sync_batch_users", with_lock=False)
    return state


async def wait_until(predicate, timeout=5):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["grpc", "rest"])
async def test_explicit_per_user_fallback_still_uses_original_transport(monkeypatch, transport):
    node = make_node(transport)
    base = GrpcNode if transport == "grpc" else RestNode
    users = [User(email="retry")]
    fallback = AsyncMock(return_value=users)
    monkeypatch.setattr(base, "_sync_batch_users", fallback)
    chunked = AsyncMock(return_value=[])
    monkeypatch.setattr(node, "sync_users_chunked", chunked)
    try:
        await node.connect("0.5.4", "26.3.27")
        assert await node._sync_batch_users(users) is users
        fallback.assert_awaited_once_with(users)
        chunked.assert_not_awaited()
    finally:
        await close_node(node)


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["grpc", "rest"])
async def test_queued_sync_keeps_legacy_node_protocol(monkeypatch, transport):
    node = make_node(transport)
    base = GrpcNode if transport == "grpc" else RestNode
    fallback = AsyncMock(return_value=[])
    monkeypatch.setattr(base, "_sync_batch_users", fallback)
    chunked = AsyncMock(return_value=[])
    monkeypatch.setattr(node, "sync_users_chunked", chunked)
    try:
        await node.connect("0.1.0", "26.3.27")
        await node.update_users([User(email="legacy")])
        await wait_until(lambda: fallback.await_count == 1)
        assert fallback.await_args.args[0][0].email == "legacy"
        chunked.assert_not_awaited()
    finally:
        await close_node(node)


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["grpc", "rest"])
async def test_update_enqueued_during_an_empty_claim_is_delivered_without_another_wake(monkeypatch, transport):
    """The lost-wake interleaving: a sibling consumes the only candidate while this worker reads it."""
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    node = make_node(transport, store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    old, new = User(email="old"), User(email="new")
    await store.enqueue_users(node.node_id, [old])
    old_key = store._pending_key(node.node_id, old.email)
    reading_old, resume_old = asyncio.Event(), asyncio.Event()
    original_get = kv.get

    async def delayed_get(key):
        if key == old_key and asyncio.current_task() is node._sync_worker_task:
            reading_old.set()
            await resume_old.wait()
        return await original_get(key)

    kv.get = delayed_get
    try:
        await node.connect("0.5.4", "26.3.27")
        await asyncio.wait_for(reading_old.wait(), 2)
        await node.update_user(new)
        sibling = await store.claim_users(node.node_id, "sibling", limit=1, lease_seconds=30)
        assert [item.user.email for item in sibling] == ["old"]
        await store.ack_users(node.node_id, [item.token for item in sibling])
        resume_old.set()
        await wait_until(lambda: "new" in state.users)
        await asyncio.wait_for(node._sync_worker_task, 5)
        assert not any(key.startswith(f"p.{node.node_id}.") for key in kv._data)
    finally:
        resume_old.set()
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_update_that_races_the_idle_exit_restarts_delivery(monkeypatch):
    """An update landing while the bridge loop winds down must not strand behind a still-running task."""
    node = make_node("grpc")
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    calls = 0
    original = GrpcNode._sync_worker

    async def exiting_loop(self):
        nonlocal calls
        calls += 1
        if calls == 1:
            # Simulate the idle timeout firing just as an update arrives: the
            # base loop returns while the wake signal is already set again.
            await self.update_user(User(email="late"))
            assert self._sync_worker_task is not None and not self._sync_worker_task.done()
            return
        await original(self)

    monkeypatch.setattr(GrpcNode, "_sync_worker", exiting_loop)
    try:
        await node.connect("0.5.4", "26.3.27")
        await wait_until(lambda: "late" in state.users)
        assert calls >= 2
    finally:
        await close_node(node)


@pytest.mark.asyncio
async def test_repeated_updates_around_idle_exits_are_all_delivered(monkeypatch):
    node = make_node("grpc")
    node._worker_idle_timeout = 0.01
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    try:
        await node.connect("0.5.4", "26.3.27")
        for number in range(60):
            await asyncio.sleep(0.008 + (number % 5) * 0.002)
            await node.update_user(User(email=f"u{number}"))
        await wait_until(lambda: len(state.users) == 60)
    finally:
        await close_node(node)


@pytest.mark.asyncio
async def test_worker_backs_off_then_recovers_from_store_errors_without_an_external_wake(monkeypatch):
    node = make_node("grpc")
    node._sync_poll_interval = 0.01
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    store = node._user_sync_store
    original_claim = store.claim_users
    failures = 0
    timeline = []

    async def flaky_claim(*args, **kwargs):
        nonlocal failures
        timeline.append(asyncio.get_running_loop().time())
        if failures < 3:
            failures += 1
            raise RuntimeError("store unavailable")
        return await original_claim(*args, **kwargs)

    monkeypatch.setattr(store, "claim_users", flaky_claim)
    try:
        await node.connect("0.5.4", "26.3.27")
        await node.update_user(User(email="u"))
        await wait_until(lambda: "u" in state.users, timeout=10)
        assert failures == 3
        gaps = [later - earlier for earlier, later in itertools.pairwise(timeline)]
        assert gaps[0] < gaps[1] < gaps[2]  # exponential backoff between re-entries
    finally:
        await close_node(node)


@pytest.mark.asyncio
async def test_transient_store_error_during_claim_does_not_strand_pending_work(monkeypatch):
    """One failed KV write inside the real claim path must not turn into an idle exit on durable work."""
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    original_update = kv.update
    injected = 0

    async def flaky_update(key, value, last=None):
        nonlocal injected
        if injected == 0 and b'"claim":' in value:
            injected += 1
            raise nats_errors.TimeoutError()
        return await original_update(key, value, last=last)

    kv.update = flaky_update
    try:
        await store.enqueue_users(node.node_id, [User(email="u")])
        await node.connect("0.5.4", "26.3.27")  # the connect wake is the only wake this work ever gets
        await wait_until(lambda: "u" in state.users, timeout=10)
        assert injected == 1
        await asyncio.wait_for(node._sync_worker_task, 10)
        assert (await store.capture_queued(node.node_id)) == ({}, 0)
    finally:
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_disconnect_keeps_queued_work_for_the_next_attachment(monkeypatch):
    store = NatsUserSyncStore(MemoryCasKv())
    node = make_node("grpc", store, sync_lease_seconds=0.3)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    state.gate = asyncio.Event()
    try:
        await node.connect("0.5.4", "26.3.27")
        await node.update_user(User(email="in-flight"))
        await asyncio.wait_for(state.delta_started.wait(), 2)
        await store.enqueue_users(node.node_id, [User(email="queued")])
        await node.disconnect()  # cancels the worker mid-delivery; nothing is cleared
        state.gate.set()
        assert {item.user.email for item in await store.claim_users(node.node_id, "inspector", 10, 0)} == {"queued"}
        await asyncio.sleep(0.35)  # the cancelled delivery's claim and the inspector's claim expire
        await node.connect("0.5.4", "26.3.27")
        await wait_until(lambda: {"in-flight", "queued"} <= set(state.users))
    finally:
        state.gate.set()
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_delta_delivered_across_a_full_snapshot_is_reapplied_from_current_state(monkeypatch):
    """Check-to-send window: the worker passes the fence check, the snapshot starts, the delta lands
    after the snapshot's database read, and the ack happens only after the fence was released."""
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    state.gate = asyncio.Event()
    register_refresh_handler(
        AsyncMock(side_effect=lambda node_id, emails: [User(email=e, inbounds=["db"]) for e in emails])
    )
    try:
        await node.connect("0.5.4", "26.3.27")
        await node.update_user(User(email="u", inbounds=["delta"]))
        await asyncio.wait_for(state.delta_started.wait(), 2)  # claimed at generation 0, send in flight
        token = await store.begin_full_sync(node.node_id, "other-worker", 120)
        assert (await store.capture_queued(node.node_id))[1] == 1  # the in-flight claim is visible
        # The other worker's snapshot was read before the delta existed and lands first.
        await state.apply_snapshot([User(email="u", inbounds=["snapshot-old"])])
        await store.end_full_sync(node.node_id, token)
        state.gate.set()  # the delta lands after the snapshot; its ack sees a newer generation
        await wait_until(lambda: state.users.get("u") == ["db"])
        assert len(state.deltas) == 2
        await asyncio.wait_for(node._sync_worker_task, 5)
        assert not any(key.startswith(f"p.{node.node_id}.") for key in kv._data)
    finally:
        register_refresh_handler(None)
        state.gate.set()
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_worker_defers_claims_while_a_snapshot_is_fenced_and_resumes_after(monkeypatch):
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    try:
        await node.connect("0.5.4", "26.3.27")
        token = await store.begin_full_sync(node.node_id, "other-worker", 120)
        await node.update_user(User(email="during"))
        await asyncio.sleep(0.1)
        assert state.deltas == []
        await store.end_full_sync(node.node_id, token)
        await wait_until(lambda: "during" in state.users)
    finally:
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_unconfirmed_ack_leaves_a_marker_resolved_from_the_source_of_truth(monkeypatch):
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    state.gate = asyncio.Event()
    register_refresh_handler(
        AsyncMock(side_effect=lambda node_id, emails: [User(email=e, inbounds=["db"]) for e in emails])
    )
    try:
        await node.connect("0.5.4", "26.3.27")
        await node.update_user(User(email="u", inbounds=["old"]))
        await asyncio.wait_for(state.delta_started.wait(), 2)
        # A newer state is queued while ours is in flight; it keeps our claim visible.
        await store.enqueue_users(node.node_id, [User(email="u", inbounds=["newer"])])
        assert await store.claim_users(node.node_id, "other", 10, 30) == []
        # The entry vanishes underneath our acknowledgement (delivered elsewhere / drained).
        await kv.delete(store._pending_key(node.node_id, "u"))
        state.gate.set()  # our old payload lands last
        await wait_until(lambda: state.users.get("u") == ["db"])
        await asyncio.wait_for(node._sync_worker_task, 5)
    finally:
        register_refresh_handler(None)
        state.gate.set()
        await close_node(node)
        await store.close()


class FakeDBNode:
    def __init__(self, node):
        self.node = node


async def make_manager(node):
    manager = NodeManager()
    manager._nodes[1] = node
    return manager


@pytest.mark.asyncio
@pytest.mark.parametrize("flush", [True, False])
async def test_sync_full_covers_users_created_after_the_snapshot_was_requested(monkeypatch, flush):
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    manager = await make_manager(node)
    created = User(email="created-later", inbounds=["in"])

    async def load_users():
        # The database read happens inside the fence; a user created right now
        # is either in this snapshot or still queued behind the fence.
        await node.update_user(created)
        return [User(email="existing", inbounds=["in"])]

    try:
        await store.enqueue_users(node.node_id, [User(email="queued-before", inbounds=["in"])])
        await manager.sync_full(1, load_users, flush_pending=flush)
        assert state.snapshots == [["existing"]]
        assert "created-later" not in state.users  # queued behind the fence, not lost
        await node.connect("0.5.4", "26.3.27")
        await wait_until(lambda: "created-later" in state.users)
        if flush:
            assert "queued-before" not in state.users  # retired: the snapshot's database read covered it
        else:
            await wait_until(lambda: "queued-before" in state.users)
        await asyncio.wait_for(node._sync_worker_task, 5)
        assert not any(key.startswith(f"p.{node.node_id}.") for key in kv._data)
    finally:
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["loader", "rpc"])
async def test_failed_full_sync_leaves_queued_work_deliverable(monkeypatch, failure):
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    manager = await make_manager(node)

    async def load_users():
        if failure == "loader":
            raise RuntimeError("database unavailable")
        return []

    async def failing_full(users, flush_pending=False, timeout=None):
        raise NodeAPIError(-1, "Request timed out")

    if failure == "rpc":
        node.sync_users = failing_full
    try:
        await store.enqueue_users(node.node_id, [User(email="queued", inbounds=["in"])])
        await store.request_refresh(node.node_id, ["marked"])
        with pytest.raises((RuntimeError, NodeAPIError)):
            await manager.sync_full(1, load_users, flush_pending=True)
        assert len([key for key in kv._data if key.startswith(f"p.{node.node_id}.")]) == 2
        register_refresh_handler(AsyncMock(return_value=[User(email="marked", inbounds=["db"])]))
        await node.connect("0.5.4", "26.3.27")
        await wait_until(lambda: {"queued", "marked"} <= set(state.users))
    finally:
        register_refresh_handler(None)
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_full_sync_waits_for_in_flight_delivery_before_reading_the_snapshot(monkeypatch):
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    node = make_node("grpc", store, sync_lease_seconds=0.5)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    state.gate = asyncio.Event()
    manager = await make_manager(node)
    order = []

    async def load_users():
        order.append("snapshot-read")
        return []

    try:
        await node.connect("0.5.4", "26.3.27")
        await node.update_user(User(email="slow"))
        await asyncio.wait_for(state.delta_started.wait(), 2)
        sync = asyncio.create_task(manager.sync_full(1, load_users, flush_pending=True))
        await asyncio.sleep(0.1)
        assert order == []  # blocked on the in-flight claim
        state.gate.set()
        await sync
        assert order == ["snapshot-read"] and state.deltas == [["slow"]]
    finally:
        state.gate.set()
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_concurrent_full_sync_on_another_worker_is_rejected():
    kv = MemoryCasKv()
    first, second = NatsUserSyncStore(kv), NatsUserSyncStore(kv)
    node = make_node("grpc", first)
    other = make_node("grpc", second, node_id=node.node_id)
    try:
        async with node.full_sync_fence():
            with pytest.raises(NodeAPIError) as info:
                async with other.full_sync_fence():
                    pass
            assert info.value.code == 409
        async with other.full_sync_fence():
            pass
    finally:
        await close_node(node)
        await close_node(other)
        await first.close()
        await second.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("loss", ["stolen", "renewal_errors"])
async def test_full_sync_that_loses_its_fence_lease_sends_and_retires_nothing(monkeypatch, loss):
    kv = MemoryCasKv()
    store, rival = NatsUserSyncStore(kv), NatsUserSyncStore(kv)
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    manager = await make_manager(node)
    monkeypatch.setattr(bridge_module, "FULL_SYNC_LEASE_SECONDS", 0.2)
    if loss == "renewal_errors":
        monkeypatch.setattr(store, "renew_full_sync", AsyncMock(side_effect=RuntimeError("nats down")))

    async def slow_loader():
        if loss == "stolen":
            # The lease lapses (clock skew / stalled renewal) and another worker takes the fence.
            doc, rev = await kv_get_json(kv, store._fence_key(node.node_id))
            doc["until"] = 0
            await kv.update(store._fence_key(node.node_id), json.dumps(doc).encode(), last=rev)
            assert await rival.begin_full_sync(node.node_id, "rival", 30) is not None
        await asyncio.sleep(0.5)
        return [User(email="snapshot", inbounds=["in"])]

    try:
        await store.enqueue_users(node.node_id, [User(email="queued", inbounds=["in"])])
        with pytest.raises(NodeAPIError) as info:
            await manager.sync_full(1, slow_loader, flush_pending=True)
        assert info.value.code == 409
        assert state.snapshots == []  # nothing was sent on a fence we no longer own
        assert len([key for key in kv._data if key.startswith(f"p.{node.node_id}.")]) == 1  # nothing retired
    finally:
        await close_node(node)
        await store.close()
        await rival.close()


@pytest.mark.asyncio
async def test_full_sync_fails_closed_when_deliveries_never_quiesce(monkeypatch):
    kv = MemoryCasKv()
    store, other = NatsUserSyncStore(kv), NatsUserSyncStore(kv)
    node = make_node("grpc", store, sync_lease_seconds=0.2)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    manager = await make_manager(node)
    monkeypatch.setattr(bridge_module, "FULL_SYNC_LEASE_SECONDS", 5.0)
    loaded = []
    try:
        await store.enqueue_users(node.node_id, [User(email="u", inbounds=["in"])])
        # Another worker's claim keeps getting refreshed (its lease never lapses).
        claimed = await other.claim_users(node.node_id, "other", 10, 60)
        assert len(claimed) == 1
        with pytest.raises(NodeAPIError) as info:
            await manager.sync_full(1, lambda: asyncio.sleep(0, result=loaded), flush_pending=True)
        assert info.value.code == 503
        assert state.snapshots == [] and loaded == []
        assert len([key for key in kv._data if key.startswith(f"p.{node.node_id}.")]) == 1
        assert not await store.full_sync_active(node.node_id)
    finally:
        await close_node(node)
        await store.close()
        await other.close()


@pytest.mark.asyncio
async def test_fence_hold_reports_expiry_even_before_the_renewal_task_notices():
    store = NatsUserSyncStore(MemoryCasKv())
    node = make_node("grpc", store)
    try:
        async with node.full_sync_fence(lease_seconds=60) as held:
            held.check()
            held.until = 0  # the lease deadline passed while a renewal was still in flight
            with pytest.raises(NodeAPIError):
                held.check()
    finally:
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("node_version", ["0.5.4", "0.1.0"])
@pytest.mark.parametrize("superseded_by", ["full_sync_retirement", "newer_acknowledged_state"])
async def test_delivery_blocked_past_its_claim_lease_is_never_sent(monkeypatch, node_version, superseded_by):
    """A worker parked behind the node lock (chunked) or a stalled per-user stream (legacy) past its
    lease must not send after a full snapshot retired the entry or a newer state was acknowledged."""
    kv = MemoryCasKv()
    store, other = NatsUserSyncStore(kv), NatsUserSyncStore(kv)
    node = make_node("grpc", store, sync_lease_seconds=2.0)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    legacy = node_version == "0.1.0"
    if legacy:
        state.gate = asyncio.Event()  # the per-user stream stalls inside the transport
    try:
        await node.connect(node_version, "26.3.27")
        block = contextlib.nullcontext() if legacy else node._node_lock  # a Start/full-sync RPC holds the node lock
        async with block:
            await node.update_user(User(email="u", inbounds=["old"]))
            await asyncio.sleep(0.3)  # claimed; the send is now blocked
            # A sibling's full snapshot begins: no further claims by this worker until it ends.
            token = await other.begin_full_sync(node.node_id, "other", 120)
            await asyncio.sleep(2.2)  # the lease is over; the blocked send was cancelled before that
            if superseded_by == "full_sync_retirement":
                captured, active = await other.capture_queued(node.node_id)
                assert active == 0 and len(captured) == 1
                await state.apply_snapshot([User(email="u", inbounds=["snapshot"])])
                assert await other.retire_captured(node.node_id, captured) == 1
                expected = ["snapshot"]
            else:
                await other.enqueue_users(node.node_id, [User(email="u", inbounds=["newer"])])
                newer = await other.claim_users(node.node_id, "other", 10, 30)
                assert [list(item.user.inbounds) for item in newer] == [["newer"]]
                state.users["u"] = ["newer"]
                assert await other.ack_users(node.node_id, [item.token for item in newer]) == []
                expected = ["newer"]
        if legacy:
            state.gate.set()
        await asyncio.sleep(0.3)
        await other.end_full_sync(node.node_id, token)
        await asyncio.sleep(0.5)
        assert state.deltas == []  # the stale payload was never sent, before or after unblocking
        assert state.users["u"] == expected
        assert not any(key.startswith(f"p.{node.node_id}.") for key in kv._data)
    finally:
        if state.gate is not None:
            state.gate.set()
        await close_node(node)
        await store.close()
        await other.close()


@pytest.mark.asyncio
async def test_slow_send_is_cut_before_its_claim_lease_expires(monkeypatch):
    store = NatsUserSyncStore(MemoryCasKv())
    node = make_node("grpc", store, sync_lease_seconds=2.0)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    state.gate = asyncio.Event()  # the stream never completes
    try:
        await node.connect("0.5.4", "26.3.27")
        await node.update_user(User(email="u"))
        await asyncio.wait_for(state.delta_started.wait(), 2)
        deadline = node._delivery_deadline
        assert node._delivery_budget() > 0
        await asyncio.sleep(1.6)  # past the budget (lease minus margin), before the lease itself
        assert time.time() < deadline
        # The send was cancelled by the deadline and the payload is queued again, unsent.
        assert state.deltas == []
        captured, active = await store.capture_queued(node.node_id)
        assert len(captured) + active == 1
    finally:
        state.gate.set()
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_fence_lease_is_renewed_while_the_snapshot_is_slow():
    store = NatsUserSyncStore(MemoryCasKv())
    node = make_node("grpc", store)
    try:
        async with node.full_sync_fence(lease_seconds=0.3):
            await asyncio.sleep(0.5)
            assert await store.full_sync_active(node.node_id)
        assert not await store.full_sync_active(node.node_id)
    finally:
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_in_memory_store_capture_holds_entries_and_settles_after_snapshot(monkeypatch):
    node = make_node("grpc")
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    manager = await make_manager(node)
    store = node._user_sync_store
    await store.enqueue_users(node.node_id, [User(email="a"), User(email="b")])
    try:
        captured = await node.capture_queued_work()
        assert {item.user.email for item in captured} == {"a", "b"}
        assert await store.claim_users(node.node_id, "x", 10, 30) == []  # held, not deleted
        await node.release_queued_work(captured)
        assert {item.user.email for item in await store.claim_users(node.node_id, "x", 10, 0)} == {"a", "b"}
        await asyncio.sleep(0.01)
        await manager.sync_full(1, lambda: asyncio.sleep(0, result=[]), flush_pending=True)
        assert await store.claim_users(node.node_id, "x", 10, 30) == []
        assert state.snapshots == [[]]
    finally:
        await close_node(node)


@pytest.mark.asyncio
async def test_bulk_updates_use_the_fenced_durable_queue(monkeypatch):
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    manager = await make_manager(node)
    try:
        await node.connect("0.5.4", "26.3.27")
        token = await store.begin_full_sync(node.node_id, "other", 120)
        await manager._sync_users_to_node(1, node, [User(email=f"bulk-{n}", inbounds=["in"]) for n in range(150)])
        await asyncio.sleep(0.2)
        assert state.deltas == []  # recorded durably, held behind the fence
        captured, _ = await store.capture_queued(node.node_id)
        assert len(captured) == 150
        await store.end_full_sync(node.node_id, token)
        await wait_until(lambda: len(state.users) == 150)
        assert all(1 <= len(batch) <= 100 for batch in state.deltas)
    finally:
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_bulk_state_committed_after_an_older_queued_payload_wins(monkeypatch):
    """Queued enabled-v1, then a bulk disable commits: the node must end disabled even if the
    first delivery attempt fails."""
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    manager = await make_manager(node)
    attempts = 0
    original_delta = state.apply_delta

    async def flaky_delta(users):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return list(users)  # first delivery fails outright
        return await original_delta(users)

    state.apply_delta = flaky_delta
    try:
        await store.enqueue_users(node.node_id, [User(email="u", inbounds=["enabled-v1"])])
        await manager._sync_users_to_node(1, node, [User(email="u", inbounds=[])])  # disabled-v2
        await node.connect("0.5.4", "26.3.27")
        await wait_until(lambda: "u" in state.users, timeout=10)
        assert state.users["u"] == [] and attempts == 2
        await asyncio.wait_for(node._sync_worker_task, 5)
        assert not any(key.startswith(f"p.{node.node_id}.") for key in kv._data)
    finally:
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_refresh_request_never_displaces_a_queued_payload_or_an_active_claim(monkeypatch):
    kv = MemoryCasKv()
    store, other = NatsUserSyncStore(kv), NatsUserSyncStore(kv)
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    register_refresh_handler(
        AsyncMock(side_effect=lambda node_id, emails: [User(email=e, inbounds=["db"]) for e in emails])
    )
    try:
        await store.enqueue_users(node.node_id, [User(email="claimed", inbounds=["payload"])])
        claimed = await other.claim_users(node.node_id, "other", 10, 30)
        assert [item.user.email for item in claimed] == ["claimed"]
        await store.enqueue_users(node.node_id, [User(email="queued", inbounds=["payload"])])
        await node.request_refresh([User(email="queued"), User(email="claimed"), User(email="fresh")])
        # Raw queue invariants: the queued payload and the sibling's claim are untouched, only "fresh" got a marker.
        docs = {
            json.loads(v)["email"]: json.loads(v)
            for k, (v, _) in kv._data.items()
            if k.startswith(f"p.{node.node_id}.")
        }
        assert "user" in docs["queued"] and "refresh" not in docs["queued"]
        assert docs["claimed"]["claim"]["worker"] == "other" and "user" in docs["claimed"]
        assert docs["fresh"] == {"email": "fresh", "refresh": True}
        _, active = await store.capture_queued(node.node_id)
        assert active == 1  # the sibling's in-flight claim is still visible
        await node.connect("0.5.4", "26.3.27")
        await wait_until(lambda: {"queued", "fresh"} <= set(state.users))
        # Delivery itself always sends the state read from the source of truth at send time.
        assert state.users["queued"] == ["db"] and state.users["fresh"] == ["db"]
        assert "claimed" not in state.users  # owned by the other worker
        await other.ack_users(node.node_id, [item.token for item in claimed])
    finally:
        register_refresh_handler(None)
        await close_node(node)
        await store.close()
        await other.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("shared_store", [False, True])
async def test_edits_queued_in_reverse_commit_order_converge_to_the_database_state(monkeypatch, shared_store):
    """Edit A (disable) commits first, edit B (new inbounds) second; A's enqueue lands last."""
    store = NatsUserSyncStore(MemoryCasKv()) if shared_store else None
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    database = {"u": ["v2"]}  # final committed state is B's
    register_refresh_handler(
        AsyncMock(side_effect=lambda node_id, emails: [User(email=e, inbounds=database.get(e, [])) for e in emails])
    )
    try:
        await node.connect("0.5.4", "26.3.27")
        await node.update_user(User(email="u", inbounds=["v2"]))  # B's serialization, enqueued first
        await node.update_user(User(email="u", inbounds=[]))  # A's older serialization, enqueued last
        await wait_until(lambda: state.users.get("u") == ["v2"], timeout=10)
        await asyncio.wait_for(node._sync_worker_task, 10)
        assert state.users["u"] == ["v2"]  # never regressed to A's state
    finally:
        register_refresh_handler(None)
        await close_node(node)
        if store is not None:
            await store.close()


@pytest.mark.asyncio
async def test_stale_single_update_after_a_bulk_update_converges(monkeypatch):
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    manager = await make_manager(node)
    database = {f"u{n}": ["bulk-v2"] for n in range(5)}
    register_refresh_handler(
        AsyncMock(side_effect=lambda node_id, emails: [User(email=e, inbounds=database.get(e, [])) for e in emails])
    )
    try:
        await manager._sync_users_to_node(1, node, [User(email=f"u{n}", inbounds=["bulk-v2"]) for n in range(5)])
        await store.enqueue_users(node.node_id, [User(email="u2", inbounds=["single-v1"])])  # older edit, later enqueue
        await node.connect("0.5.4", "26.3.27")
        await wait_until(lambda: len(state.users) == 5, timeout=10)
        await asyncio.wait_for(node._sync_worker_task, 10)
        assert state.users == database
    finally:
        register_refresh_handler(None)
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_failed_current_state_read_requeues_the_batch_and_never_acknowledges_stale_state(monkeypatch):
    store = NatsUserSyncStore(MemoryCasKv())
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    attempts = 0

    async def flaky(node_id, emails):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("database unavailable")
        return [User(email=e, inbounds=["db"]) for e in emails]

    register_refresh_handler(flaky)
    try:
        await node.connect("0.5.4", "26.3.27")
        await node.update_user(User(email="u", inbounds=["queued"]))
        await wait_until(lambda: state.users.get("u") == ["db"], timeout=10)
        assert attempts == 2 and state.deltas == [["u"]]  # nothing was sent while the read was failing
        await asyncio.wait_for(node._sync_worker_task, 10)
        assert (await store.capture_queued(node.node_id)) == ({}, 0)
    finally:
        register_refresh_handler(None)
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_start_snapshot_and_start_rpc_run_inside_the_fence(monkeypatch):
    from app.operation.node import NodeOperation

    store = NatsUserSyncStore(MemoryCasKv())
    node = make_node("grpc", store)
    seen = []

    async def load():
        seen.append(("load", await store.full_sync_active(node.node_id)))
        return []

    async def start(**kwargs):
        seen.append(("start", await store.full_sync_active(node.node_id)))
        return SimpleNamespace(started=True, node_version="0.5.4", core_version="26.3.27")

    monkeypatch.setattr(node, "get_lifecycle_state", AsyncMock(return_value=None))
    monkeypatch.setattr(node, "start", start)
    core = SimpleNamespace(type=None, inbounds=[], protocols=frozenset(), to_str=lambda: "{}")
    db_node = SimpleNamespace(id=1, name="node", keep_alive=0)
    try:
        info = await NodeOperation._start_or_attach_node(node, db_node, core, load, None)
        assert info.started
        assert seen == [("load", True), ("start", True)]
        assert not await store.full_sync_active(node.node_id)
    finally:
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_start_yields_to_a_snapshot_in_progress_elsewhere(monkeypatch):
    from app.operation.node import NodeOperation

    kv = MemoryCasKv()
    store, other = NatsUserSyncStore(kv), NatsUserSyncStore(kv)
    node = make_node("grpc", store)
    monkeypatch.setattr(node, "get_lifecycle_state", AsyncMock(return_value=None))
    monkeypatch.setattr(node, "start", AsyncMock())
    core = SimpleNamespace(type=None, inbounds=[], protocols=frozenset(), to_str=lambda: "{}")
    db_node = SimpleNamespace(id=1, name="node", keep_alive=0)
    try:
        token = await other.begin_full_sync(node.node_id, "other", 120)
        with pytest.raises(NodeAPIError) as info:
            await NodeOperation._start_or_attach_node(node, db_node, core, [], None)
        assert info.value.code == 409
        node.start.assert_not_awaited()
        await other.end_full_sync(node.node_id, token)
    finally:
        await close_node(node)
        await store.close()
        await other.close()


@pytest.mark.asyncio
async def test_refresh_handler_registration_survives_missing_handler():
    store = NatsUserSyncStore(MemoryCasKv())
    node = make_node("grpc", store)
    try:
        register_refresh_handler(None)
        with pytest.raises(RuntimeError):
            await bridge_module._resolve_refresh(node.node_id, ["1"])
    finally:
        await close_node(node)
        await store.close()


@pytest.mark.asyncio
async def test_health_transitions_do_not_lose_queued_work(monkeypatch):
    store = NatsUserSyncStore(MemoryCasKv())
    node = make_node("grpc", store)
    state = attach_fake_transport(monkeypatch, node, FakeNodeState())
    try:
        await node.connect("0.5.4", "26.3.27")
        await node.set_health(Health.BROKEN)
        await node.update_user(User(email="while-broken"))
        await asyncio.sleep(0.05)
        assert state.deltas == []
        await node.set_health(Health.HEALTHY)
        await wait_until(lambda: "while-broken" in state.users, timeout=10)
    finally:
        await close_node(node)
        await store.close()


@contextlib.asynccontextmanager
async def _noop():
    yield
