"""A user change a node failed to queue is retried, never silently dropped."""

import asyncio
import gc
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PasarGuardNodeBridge import InMemoryUserSyncStore
from PasarGuardNodeBridge.common.service_pb2 import User as ProtoUser

from app.db.models import NodeConnectionType, NodeStatus
from app.jobs import node_checker
from app.nats.kv_cas import MemoryCasKv
from app.node import NodeManager, bridge as bridge_module, sync as node_sync
from app.node.nats_memory import NatsUserSyncStore, UserSyncValueTooLargeError
from tests.test_node_bridge import FakeNodeState, attach_fake_transport, close_node, make_node, wait_until

FAST_RETRIES = (0.2, 0.05, 0.05)


class StoreDown(ConnectionError):
    pass


class FlakyStore(InMemoryUserSyncStore):
    """An in-memory queue whose writes fail like NATS that is slow or reconnecting."""

    def __init__(self, failures: int = 0):
        super().__init__()
        self.failures = failures
        self.down = False
        self.enqueue_calls = 0
        self.enqueued_sizes: list[int] = []
        self.poison: set[str] = set()  # users this store can never queue (payload too large)

    def _write(self, emails):
        self.enqueue_calls += 1
        self.enqueued_sizes.append(len(emails))
        if self.poison.intersection(emails):
            raise UserSyncValueTooLargeError("payload too large")
        if self.down or self.failures > 0:
            self.failures = max(0, self.failures - 1)
            raise StoreDown("user sync store unavailable")

    async def enqueue_users(self, node_id, users):
        self._write([user.email for user in users])
        await super().enqueue_users(node_id, users)

    async def request_refresh(self, node_id, emails):
        # Like the NATS store: a marker re-read before delivery, never written over a queued entry.
        self._write(list(emails))
        await self.enqueue_users_if_absent(node_id, [ProtoUser(email=email) for email in emails])


class Database(dict):
    """Current user state by email, as the node queue reads it before delivery."""

    def put(self, user: ProtoUser) -> ProtoUser:
        self[user.email] = user
        return user

    async def read(self, node_id, emails):
        return [self.get(email, ProtoUser(email=email)) for email in emails]


@pytest.fixture(autouse=True)
def database(monkeypatch) -> Database:
    database = Database()
    monkeypatch.setattr(bridge_module, "_refresh_handler", database.read)
    return database


def _user(user_id: int, *inbounds: str) -> ProtoUser:
    return ProtoUser(email=str(user_id), inbounds=list(inbounds))


def _wireguard_user(user_id: int, key: str, *inbounds: str) -> ProtoUser:
    user = _user(user_id, *inbounds)
    user.proxies.wireguard.public_key = key
    user.proxies.wireguard.peer_ips.append("10.0.0.5/32")
    return user


async def _cluster(monkeypatch, *stores: FlakyStore, delays=FAST_RETRIES):
    manager = NodeManager()
    manager.USER_SYNC_RETRY_DELAYS = delays
    states = []
    for node_id, store in enumerate(stores, start=1):
        node = make_node("grpc", store)
        state = attach_fake_transport(monkeypatch, node, FakeNodeState())
        await node.connect("0.5.4", "26.10.10")
        manager._nodes[node_id] = node
        states.append(state)
    return manager, states


def _pending(manager: NodeManager, node_id: int) -> set[str]:
    return set(getattr(manager, "_pending_user_syncs", {}).get(node_id) or ())


def _retrying(manager: NodeManager) -> bool:
    return any(not task.done() for task in getattr(manager, "_user_sync_retry_tasks", {}).values())


async def _settled(manager: NodeManager):
    await wait_until(lambda: not _retrying(manager))


async def _drained(store: FlakyStore, node):
    async with asyncio.timeout(5):
        while await store.has_pending(node.node_id):
            await asyncio.sleep(0.005)


async def _close(manager: NodeManager):
    if (stop := getattr(manager, "stop_user_sync_retries", None)) is not None:
        await stop()
    for node in list(manager._nodes.values()):
        await close_node(node)


def _removal_keys(monkeypatch) -> list[str]:
    """WireGuard keys that deliveries of a removed user carry to the node."""
    keys: list[str] = []
    keep = bridge_module._keep_removal_credentials

    def spy(fresh, queued):
        kept = keep(fresh, queued)
        if not fresh.inbounds:
            keys.append(kept.proxies.wireguard.public_key)
        return kept

    monkeypatch.setattr(bridge_module, "_keep_removal_credentials", spy)
    return keys


def _hold_delivery(monkeypatch, node, store) -> asyncio.Event:
    """Keep queued users undelivered (node busy) until the returned event is set."""
    node._work_available.clear()
    claim = store.claim_users
    release = asyncio.Event()

    async def held_claim(*args, **kwargs):
        await release.wait()
        return await claim(*args, **kwargs)

    monkeypatch.setattr(store, "claim_users", held_claim)
    return release


async def test_node_that_failed_to_queue_gets_the_user_after_a_retry(monkeypatch, database):
    stores = (FlakyStore(), FlakyStore(), FlakyStore(failures=1))
    manager, states = await _cluster(monkeypatch, *stores)
    try:
        with pytest.raises(StoreDown):
            await manager.update_user(database.put(_user(7, "in-a")))
        await wait_until(lambda: "7" in states[0].users and "7" in states[1].users)
        assert "7" not in states[2].users  # still waiting for its retry
        assert _pending(manager, 3) == {"7"} and not _pending(manager, 1) and not _pending(manager, 2)

        await wait_until(lambda: "7" in states[2].users)
        assert states[2].users["7"] == ["in-a"]
        assert not _pending(manager, 3)
        assert [store.enqueue_calls for store in stores] == [1, 1, 2]
    finally:
        await _close(manager)


async def test_exhausted_retries_log_the_user_and_node_and_resume_at_the_health_check(monkeypatch, caplog, database):
    stores = (FlakyStore(), FlakyStore(), FlakyStore())
    for store in stores:
        store.down = True
    manager, states = await _cluster(monkeypatch, *stores, delays=(0.01, 0.01))
    try:
        with caplog.at_level(logging.ERROR, logger=manager.logger.name):
            with pytest.raises(StoreDown):
                await manager.update_user(database.put(_user(41, "in-a")))
            await _settled(manager)
        errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
        for node_id in (1, 2, 3):
            assert any(f"for node {node_id} after 2 attempts" in message and "41" in message for message in errors)
            assert _pending(manager, node_id) == {"41"}
        assert not any("41" in state.users for state in states)

        # Still down: the health check's attempt keeps the users waiting.
        monkeypatch.setattr(node_checker, "node_manager", manager)
        monkeypatch.setattr(node_checker, "_load_health_settings", AsyncMock())
        monkeypatch.setattr(node_checker, "_in_probe_backoff", lambda db_node, node: True)

        async def health_check_all():
            for node_id, node in manager._nodes.items():
                db_node = SimpleNamespace(id=node_id, name=f"n{node_id}", status=NodeStatus.connected)
                await node_checker.process_node_health_check(db_node, node)
            await _settled(manager)

        await health_check_all()
        assert all(_pending(manager, node_id) == {"41"} for node_id in (1, 2, 3))

        # Back up: every node gets the user without a new change.
        for store in stores:
            store.down = False
        await health_check_all()
        await wait_until(lambda: all(state.users.get("41") == ["in-a"] for state in states))
        assert not any(_pending(manager, node_id) for node_id in (1, 2, 3))
    finally:
        await _close(manager)


async def test_removal_that_failed_to_queue_still_removes_the_user(monkeypatch, database):
    store = FlakyStore()
    manager, [state] = await _cluster(monkeypatch, store)
    try:
        await manager.update_user(database.put(_wireguard_user(9, "K9", "in-a")))
        await wait_until(lambda: state.users.get("9") == ["in-a"])

        store.failures = 1
        with pytest.raises(StoreDown):
            await manager.update_user(database.put(_wireguard_user(9, "K9")))  # disabled: no inbounds
        await wait_until(lambda: state.users.get("9") == [])
        await _settled(manager)
        assert not _pending(manager, 1)
    finally:
        await _close(manager)


async def test_user_deleted_while_waiting_for_a_retry_is_delivered_as_removed(monkeypatch, database):
    store = FlakyStore(failures=1)
    manager, [state] = await _cluster(monkeypatch, store)
    try:
        with pytest.raises(StoreDown):
            await manager.update_user(database.put(_user(5, "in-a")))
        del database["5"]
        await wait_until(lambda: "5" in state.users)
        assert state.users["5"] == []
        await _settled(manager)
        assert not _pending(manager, 1)
    finally:
        await _close(manager)


async def test_removed_node_drops_its_waiting_users(monkeypatch, database):
    store = FlakyStore()
    store.down = True
    manager, _states = await _cluster(monkeypatch, store, delays=(30.0,))
    node = manager._nodes[1]
    try:
        with pytest.raises(StoreDown):
            await manager.update_user(database.put(_user(3, "in-a")))
        retry = manager._user_sync_retry_tasks[1]
        assert _pending(manager, 1) == {"3"}
        await manager.remove_node(1, remote_stop=False)
        assert not _pending(manager, 1)
        assert retry.cancelled() and not _retrying(manager)
        # A late failure for the removed node is not remembered.
        manager._user_sync_failed(1, [_user(3, "in-a")], StoreDown("late"))
        assert not _pending(manager, 1) and not _retrying(manager)
    finally:
        await _close(manager)
        await close_node(node)


async def test_bulk_update_that_failed_to_queue_is_retried(monkeypatch, database):
    stores = (FlakyStore(), FlakyStore(failures=1))
    manager, states = await _cluster(monkeypatch, *stores)
    users = [database.put(_user(user_id, "in-a")) for user_id in range(100, 110)]
    try:
        await manager.update_users(users, await_dispatch=True)  # never raises
        assert _pending(manager, 2) == {user.email for user in users} and not _pending(manager, 1)
        await wait_until(lambda: len(states[0].users) == 10)
        await wait_until(lambda: len(states[1].users) == 10)
        await _settled(manager)
        assert not _pending(manager, 2)
    finally:
        await _close(manager)


async def test_successful_queueing_is_unchanged(monkeypatch, database):
    calls: list[tuple[str, int, str]] = []

    class RecordingNode:
        def __init__(self, node_id):
            self.node_id = node_id

        async def update_user(self, user):
            calls.append(("update_user", self.node_id, user.email))

        async def update_users(self, users):
            calls.append(("update_users", self.node_id, ",".join(user.email for user in users)))

    manager = NodeManager()
    for node_id in (1, 2, 3):
        manager._nodes[node_id] = RecordingNode(node_id)

    await manager.update_user(_user(1, "in-a"))
    assert calls == [("update_user", 1, "1"), ("update_user", 2, "1"), ("update_user", 3, "1")]
    assert not manager._pending_user_syncs and not manager._user_sync_retry_tasks

    # The real in-memory queue of a single process delivers once per node.
    store = FlakyStore()
    real, [state] = await _cluster(monkeypatch, store)
    try:
        await real.update_user(database.put(_user(2, "in-a")))
        await wait_until(lambda: "2" in state.users)
        await _drained(store, real._nodes[1])
        assert state.deltas == [["2"]]
        assert store.enqueue_calls == 1
        assert not real._pending_user_syncs and not real._user_sync_retry_tasks
    finally:
        await _close(real)


async def test_background_dispatch_failure_is_logged_and_retrieved(monkeypatch, caplog):
    loop = asyncio.get_running_loop()
    unhandled = []
    previous = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: unhandled.append(context))

    async def failing_dispatch(proto_user):
        await asyncio.sleep(0)
        raise StoreDown("nats reconnecting")

    monkeypatch.setattr(node_sync, "_dispatch_user_update", failing_dispatch)
    removed = SimpleNamespace(id=77, proxy_settings=SimpleNamespace(dict=dict))
    try:
        with caplog.at_level(logging.WARNING, logger="node-sync"):
            await node_sync.remove_user(removed)
            await wait_until(lambda: not node_sync._background_dispatches)
            gc.collect()
            await asyncio.sleep(0)
        assert not unhandled
        assert any("77" in record.getMessage() for record in caplog.records)
    finally:
        loop.set_exception_handler(previous)


async def test_shutdown_settles_background_dispatches_and_reports_unqueued_users(monkeypatch, caplog, database):
    started = asyncio.Event()

    async def hanging_dispatch(proto_user):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(node_sync, "_dispatch_user_update", hanging_dispatch)
    await node_sync.remove_user(SimpleNamespace(id=78, proxy_settings=SimpleNamespace(dict=dict)))
    await started.wait()
    await node_sync.drain_background_dispatches(timeout=0.05)
    assert not node_sync._background_dispatches

    store = FlakyStore()
    store.down = True
    manager, _states = await _cluster(monkeypatch, store, delays=(30.0,))
    try:
        with pytest.raises(StoreDown):
            await manager.update_user(database.put(_user(79, "in-a")))
        retry = manager._user_sync_retry_tasks[1]
        with caplog.at_level(logging.ERROR, logger=manager.logger.name):
            await manager.stop_user_sync_retries()
        assert retry.cancelled()
        assert any("79" in record.getMessage() and "node 1" in record.getMessage() for record in caplog.records)
    finally:
        await _close(manager)


async def test_old_write_failing_after_a_newer_removal_never_overrides_it(monkeypatch, database):
    # Review must-fix 1: the write of v1 (key K1) hangs; the key is reissued (K2) and the
    # user deleted, both queued fine; then v1 fails. Its retry must not bring K1 back: the
    # removal reaches the node with K2, else the node removes the old peer and K2 keeps working.
    store = FlakyStore()
    manager, [_state] = await _cluster(monkeypatch, store, delays=(0.01,))
    node = manager._nodes[1]
    keys = _removal_keys(monkeypatch)
    write = store.enqueue_users
    started, fail_now = asyncio.Event(), asyncio.Event()

    async def slow_v1(node_id, users):
        if any(user.proxies.wireguard.public_key == "K1" for user in users) and not started.is_set():
            started.set()
            await fail_now.wait()
            raise StoreDown("timeout")
        await write(node_id, users)

    monkeypatch.setattr(store, "enqueue_users", slow_v1)
    try:
        release = _hold_delivery(monkeypatch, node, store)
        v1 = asyncio.create_task(manager.update_user(database.put(_wireguard_user(5, "K1", "in-a"))))
        await asyncio.wait_for(started.wait(), 2)
        await manager.update_user(database.put(_wireguard_user(5, "K2", "in-a")))
        del database["5"]
        await manager.update_user(_wireguard_user(5, "K2"))  # removal
        fail_now.set()
        with pytest.raises(StoreDown):
            await v1
        await _settled(manager)
        assert not _pending(manager, 1)
        release.set()
        await _drained(store, node)
        assert keys == ["K2"]
    finally:
        await _close(manager)


async def test_failed_bulk_write_after_a_newer_removal_never_overrides_it(monkeypatch, database):
    # Review must-fix 1, bulk variant: U is in a large batch whose write fails late.
    store = FlakyStore()
    manager, [state] = await _cluster(monkeypatch, store, delays=(0.01,))
    node = manager._nodes[1]
    keys = _removal_keys(monkeypatch)
    write = store.enqueue_users
    started, fail_now = asyncio.Event(), asyncio.Event()

    async def slow_bulk(node_id, users):
        if len(users) > 1 and not started.is_set():
            started.set()
            await fail_now.wait()
            raise RuntimeError("failed to enqueue NATS KV key after CAS retries")
        await write(node_id, users)

    monkeypatch.setattr(store, "enqueue_users", slow_bulk)
    try:
        release = _hold_delivery(monkeypatch, node, store)
        bulk = [database.put(_wireguard_user(5, "K1", "in-a"))]
        bulk += [database.put(_user(user_id, "in-a")) for user_id in range(600, 640)]
        batch = asyncio.create_task(manager.update_users(bulk, await_dispatch=True))
        await asyncio.wait_for(started.wait(), 2)
        await manager.update_user(database.put(_wireguard_user(5, "K2", "in-a")))
        del database["5"]
        await manager.update_user(_wireguard_user(5, "K2"))
        fail_now.set()
        await batch
        await _settled(manager)
        assert not _pending(manager, 1)
        release.set()
        await _drained(store, node)
        assert keys == ["K2"]
        assert all(state.users.get(str(user_id)) == ["in-a"] for user_id in range(600, 640))
    finally:
        await _close(manager)


async def test_retry_never_writes_a_payload_it_saw_queued_meanwhile(monkeypatch, database):
    # Review must-fix 1, retry variant: v2 (K2) and the removal fail; while their retry
    # queues the user, the hung write of v1 (K1) lands. The retry must not write v1 again
    # after the removal: it only ever writes what the database holds.
    store = FlakyStore()
    manager, [_state] = await _cluster(monkeypatch, store, delays=(0.01,))
    node = manager._nodes[1]
    _removal_keys(monkeypatch)
    write, refresh = store.enqueue_users, store.request_refresh
    k1_writes: list[str] = []
    v1_started, v1_lands, v1_landed, retry_started = (asyncio.Event() for _ in range(4))
    api_k2_writes = 0

    async def scripted_write(node_id, users):
        nonlocal api_k2_writes
        keys = {user.proxies.wireguard.public_key for user in users}
        if "K1" in keys:
            k1_writes.append("K1")
            if not v1_started.is_set():
                v1_started.set()
                await v1_lands.wait()
                await write(node_id, users)
                v1_landed.set()
                return
        if "K2" in keys and api_k2_writes < 2:
            api_k2_writes += 1
            raise StoreDown("timeout")
        if not retry_started.is_set():
            retry_started.set()
            await v1_landed.wait()
        await write(node_id, users)

    async def scripted_refresh(node_id, emails):
        if not retry_started.is_set():
            retry_started.set()
            await v1_landed.wait()
        await refresh(node_id, emails)

    monkeypatch.setattr(store, "enqueue_users", scripted_write)
    monkeypatch.setattr(store, "request_refresh", scripted_refresh)
    try:
        release = _hold_delivery(monkeypatch, node, store)
        v1 = asyncio.create_task(manager.update_user(database.put(_wireguard_user(5, "K1", "in-a"))))
        await asyncio.wait_for(v1_started.wait(), 2)
        with pytest.raises(StoreDown):
            await manager.update_user(database.put(_wireguard_user(5, "K2", "in-a")))
        del database["5"]
        with pytest.raises(StoreDown):
            await manager.update_user(_wireguard_user(5, "K2"))
        await asyncio.wait_for(retry_started.wait(), 2)
        v1_lands.set()
        await v1
        await _settled(manager)
        assert not _pending(manager, 1)
        release.set()
        await _drained(store, node)
        assert k1_writes == ["K1"]  # only the API's own write of v1
    finally:
        await _close(manager)


async def test_retry_never_replaces_the_credentials_of_a_user_changed_and_deleted_after_its_read(monkeypatch, database):
    # The retry read the user with K1. Before it writes, the key changes to K2 and the user is
    # deleted; the removal is queued with K2, the key the node holds. Written over it, the retry's
    # K1 would be the only credentials left for the removal and the K2 peer would stay on the node.
    store = FlakyStore(failures=1)
    manager, [state] = await _cluster(monkeypatch, store, delays=(0.01,))
    node = manager._nodes[1]
    keys = _removal_keys(monkeypatch)
    release = _hold_delivery(monkeypatch, node, store)
    write, refresh = store.enqueue_users, store.request_refresh
    retry_writing, retry_may_finish = asyncio.Event(), asyncio.Event()

    def held(call):
        async def hold_the_retry(node_id, items):
            if store.enqueue_calls == 1 and not retry_writing.is_set():  # the retry's write
                retry_writing.set()
                await retry_may_finish.wait()
            await call(node_id, items)

        return hold_the_retry

    try:
        with pytest.raises(StoreDown):
            await manager.update_user(database.put(_wireguard_user(5, "K1", "in-a")))
        monkeypatch.setattr(store, "enqueue_users", held(write))
        monkeypatch.setattr(store, "request_refresh", held(refresh))
        await asyncio.wait_for(retry_writing.wait(), 2)
        await manager.update_user(database.put(_wireguard_user(5, "K2", "in-a")))
        del database["5"]
        await manager.update_user(_wireguard_user(5, "K2"))
        retry_may_finish.set()
        await _settled(manager)
        assert not _pending(manager, 1)
        release.set()
        await _drained(store, node)
        assert keys == ["K2"]
        assert state.users.get("5") == []
    finally:
        release.set()
        await _close(manager)


async def test_transient_failures_never_drop_a_user(monkeypatch, caplog, database):
    # Review must-fix 2: NATS flaps; writes of user 7 keep failing for a while although
    # other users are queued fine in between. User 7 stays until it is queued.
    store = FlakyStore()
    manager, [state] = await _cluster(monkeypatch, store, delays=(0.01,))
    write, refresh = store.enqueue_users, store.request_refresh
    failing = True

    async def flaky(node_id, users):
        if failing and any(user.email == "7" for user in users):
            raise StoreDown("nats timeout")
        await write(node_id, users)

    async def flaky_refresh(node_id, emails):  # the retry's write
        if failing and "7" in emails:
            raise StoreDown("nats timeout")
        await refresh(node_id, emails)

    monkeypatch.setattr(store, "enqueue_users", flaky)
    monkeypatch.setattr(store, "request_refresh", flaky_refresh)
    try:
        with caplog.at_level(logging.ERROR, logger=manager.logger.name):
            with pytest.raises(StoreDown):
                await manager.update_user(database.put(_user(7, "in-a")))
            await _settled(manager)
            for user_id in range(800, 806):
                await manager.update_user(database.put(_user(user_id, "in-a")))  # others work
                manager.resume_user_sync_retries(1)  # health check
                await _settled(manager)
                assert _pending(manager, 1) == {"7"}
        assert not any("not retried" in record.getMessage() for record in caplog.records)

        failing = False
        manager.resume_user_sync_retries(1)
        await wait_until(lambda: state.users.get("7") == ["in-a"])
        await _settled(manager)
        assert not _pending(manager, 1)
    finally:
        await _close(manager)


async def test_failure_during_a_retry_attempt_keeps_the_user(monkeypatch, database):
    # The retry read the user and is writing it when a newer change of it fails to queue;
    # the retry's write working must not count for the newer change.
    store = FlakyStore(failures=1)
    manager, [state] = await _cluster(monkeypatch, store, delays=(0.01, 0.01))
    refresh = store.request_refresh
    retry_writing, retry_may_finish = asyncio.Event(), asyncio.Event()

    async def held_retry(node_id, emails):
        if store.enqueue_calls == 1 and not retry_writing.is_set():  # the retry's write
            retry_writing.set()
            await retry_may_finish.wait()
        await refresh(node_id, emails)

    try:
        with pytest.raises(StoreDown):
            await manager.update_user(database.put(_user(8, "in-a")))
        monkeypatch.setattr(store, "request_refresh", held_retry)
        await asyncio.wait_for(retry_writing.wait(), 2)
        store.failures = 1
        with pytest.raises(StoreDown):
            await manager.update_user(database.put(_user(8, "in-b")))
        retry_may_finish.set()
        await wait_until(lambda: state.users.get("8") == ["in-b"])
        await _settled(manager)
        assert not _pending(manager, 1)
        # failed v1, the retry's write, failed v2, and the write the newer failure still needed
        assert store.enqueue_calls == 4
    finally:
        await _close(manager)


async def test_node_with_queue_down_retries_one_user_per_round(monkeypatch, database):
    # Many users waiting while the queue is down: each round writes one user at a time,
    # not all of them, so fresh changes are not stuck behind a wave of timeouts.
    store = FlakyStore()
    store.down = True
    manager, states = await _cluster(monkeypatch, store, delays=(0.01, 0.01))
    users = [database.put(_user(user_id, "in-a")) for user_id in range(200, 250)]
    try:
        await manager.update_users(users, await_dispatch=True)
        await _settled(manager)
        assert store.enqueued_sizes[0] == 50
        assert all(size == 1 for size in store.enqueued_sizes[1:])
        assert len(store.enqueued_sizes) <= 1 + 2 * 2  # two rounds, at most two probes each
        assert len(_pending(manager, 1)) == 50

        store.down = False
        manager.resume_user_sync_retries(1)
        await wait_until(lambda: len(states[0].users) == 50)
        await _settled(manager)
        assert not _pending(manager, 1)
    finally:
        await _close(manager)


async def test_payload_that_can_never_be_queued_does_not_hold_back_others(monkeypatch, caplog, database):
    store = FlakyStore()
    store.down = True
    manager, states = await _cluster(monkeypatch, store, delays=(0.01,))
    users = [database.put(_user(user_id, "in-a")) for user_id in range(300, 306)]
    try:
        await manager.update_users(users, await_dispatch=True)
        await _settled(manager)
        store.down = False
        store.poison = {"303"}
        with caplog.at_level(logging.ERROR, logger=manager.logger.name):
            manager.resume_user_sync_retries(1)
            await wait_until(lambda: len(states[0].users) == 5)
            await _settled(manager)
        assert "303" not in states[0].users
        assert not _pending(manager, 1)  # given up at once, with an error naming it
        assert any(
            "303" in record.getMessage() and "node 1" in record.getMessage() and "not retried" in record.getMessage()
            for record in caplog.records
        )

        calls = store.enqueue_calls
        await manager.update_user(database.put(_user(404, "in-a")))
        assert store.enqueue_calls == calls + 1
        assert not _retrying(manager)  # nothing left that could be queued again
    finally:
        await _close(manager)


class FlakyNatsStore(NatsUserSyncStore):
    """The NATS queue (on an in-memory KV) whose payload writes fail like NATS that is reconnecting."""

    def __init__(self):
        super().__init__(MemoryCasKv())
        self.refresh_resolver = bridge_module._resolve_refresh
        self.failures = 0

    async def enqueue_users(self, node_id, users):
        if self.failures > 0:
            self.failures -= 1
            raise StoreDown("user sync store unavailable")
        await super().enqueue_users(node_id, users)


async def test_removal_that_failed_to_queue_during_a_delivery_still_removes_the_user(monkeypatch, database):
    # The worker has read the user as active and is sending it when the user is deleted and
    # the removal fails to queue. The retry finds the entry claimed: the delivery's
    # acknowledgement must fail, so the entry is delivered once more and removes the user.
    store = FlakyNatsStore()
    manager, [state] = await _cluster(monkeypatch, store, delays=(0.01,))
    node = manager._nodes[1]
    read = database.read
    in_delivery, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def slow_first_read(node_id, emails):
        nonlocal calls
        calls += 1
        result = await read(node_id, emails)
        if calls == 1:  # the delivery read: the state is taken, the send is slow
            in_delivery.set()
            await release.wait()
        return result

    monkeypatch.setattr(bridge_module, "_refresh_handler", slow_first_read)
    try:
        await manager.update_user(database.put(_user(5, "in-a")))
        await asyncio.wait_for(in_delivery.wait(), 2)
        del database["5"]
        store.failures = 1
        with pytest.raises(StoreDown):
            await manager.update_user(_user(5))
        await _settled(manager)
        assert not _pending(manager, 1)
        release.set()
        await _drained(store, node)
        assert state.users.get("5") == []
    finally:
        release.set()
        await _close(manager)
        await store.close()


class LandsThenFails(bridge_module.MemoryUserSyncStore):
    """The process-local queue (no NATS) whose write lands and then reports a failure."""

    fail_after_write = 0

    async def enqueue_users(self, node_id, users):
        await super().enqueue_users(node_id, users)
        if self.fail_after_write:
            self.fail_after_write -= 1
            raise StoreDown("ack lost")


async def test_memory_store_retry_of_a_deleted_user_keeps_its_queued_credentials(monkeypatch, database):
    # The retry reads a removal without credentials (the user is gone); the queued removal
    # keeps K2, so the node can still find the WireGuard peer.
    store = LandsThenFails()
    manager, [state] = await _cluster(monkeypatch, store, delays=(0.01,))
    node = manager._nodes[1]
    keys = _removal_keys(monkeypatch)
    release = _hold_delivery(monkeypatch, node, store)
    try:
        store.fail_after_write = 1
        with pytest.raises(StoreDown):
            await manager.update_user(_wireguard_user(5, "K2"))  # removal of a deleted user
        await _settled(manager)
        assert not _pending(manager, 1)
        release.set()
        await _drained(store, node)
        assert state.users.get("5") == []
        assert keys == ["K2"]
    finally:
        release.set()
        await _close(manager)


async def test_memory_store_refresh_keeps_a_queued_payload_and_queues_a_missing_one():
    store = bridge_module.MemoryUserSyncStore()
    await store.enqueue_users("1", [_wireguard_user(7, "K2")])
    await store.refresh_users("1", [_user(7), _wireguard_user(8, "K8")])
    claimed = {item.user.email: item.user for item in await store.claim_users("1", "w", 10, 30)}
    assert claimed["7"].proxies.wireguard.public_key == "K2"
    assert claimed["8"].proxies.wireguard.public_key == "K8"


async def test_memory_store_refresh_outlives_a_delivery_claimed_before_it():
    # A delivery claimed before the refresh may carry an older read: its ack must not settle the entry.
    store = bridge_module.MemoryUserSyncStore()
    await store.enqueue_users("1", [_user(9, "in-a")])
    [item] = await store.claim_users("1", "w", 10, 30)
    await store.refresh_users("1", [_user(9)])
    await store.ack_users("1", [item.token])
    assert await store.has_pending("1")
    [again] = await store.claim_users("1", "w", 10, 30)
    assert again.user.email == "9"
    await store.ack_users("1", [again.token])
    assert not await store.has_pending("1")


def test_nodes_without_nats_share_the_refreshing_memory_store(monkeypatch):
    monkeypatch.setattr("app.node.get_bridge_memory", lambda: (None, None, "w"))
    node = SimpleNamespace(
        connection_type=NodeConnectionType.grpc,
        address="127.0.0.1",
        port=1,
        api_port=2,
        server_ca="",
        certificate_sha256=None,
        api_key="k",
        name="n",
        default_timeout=10,
        internal_timeout=15,
        proxy_url=None,
        id=3,
        usage_coefficient=1.0,
    )
    kwargs = NodeManager()._create_node_kwargs(node)
    assert kwargs["user_sync_store"] is bridge_module.get_memory_user_sync_store()


async def test_shutdown_leaves_no_retry_task_behind(monkeypatch, database):
    store = FlakyStore()
    manager, [_state] = await _cluster(monkeypatch, store, delays=(30.0,))
    write = store.enqueue_users

    async def hang(node_id, users):
        await asyncio.Event().wait()

    monkeypatch.setattr(store, "enqueue_users", hang)
    try:
        await manager.update_users([database.put(_user(61, "in-a"))])  # the background batch hangs
        await asyncio.sleep(0.05)
        await manager.stop_user_sync_retries()
        left = [task for task in asyncio.all_tasks() if "user-sync-retry" in task.get_name() and not task.done()]
        assert not left
        assert not manager._user_sync_retry_tasks
    finally:
        monkeypatch.setattr(store, "enqueue_users", write)
        await _close(manager)


@pytest.mark.parametrize("single", [False, True], ids=["update_users", "update_user"])
async def test_cancelled_queueing_is_retried(monkeypatch, database, single):
    store = FlakyStore()
    manager, [state] = await _cluster(monkeypatch, store, delays=(0.3,))
    write = store.enqueue_users
    started = asyncio.Event()
    hold = True

    async def hanging(node_id, users):
        if hold:
            started.set()
            await asyncio.Event().wait()
        await write(node_id, users)

    monkeypatch.setattr(store, "enqueue_users", hanging)
    try:
        user = database.put(_user(63, "in-a"))
        call = manager.update_user(user) if single else manager.update_users([user], await_dispatch=True)
        caller = asyncio.create_task(call)
        await asyncio.wait_for(started.wait(), 2)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        hold = False
        assert _pending(manager, 1) == {"63"}
        await wait_until(lambda: state.users.get("63") == ["in-a"])
        await _settled(manager)
        assert not _pending(manager, 1)
    finally:
        await _close(manager)
