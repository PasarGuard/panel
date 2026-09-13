"""CAS semantics for NATS-backed bridge user-sync + lifecycle memory."""

import asyncio
import json
import time
from unittest.mock import AsyncMock

import nats.errors as nats_errors
import pytest
from nats.js.errors import KeyWrongLastSequenceError
from PasarGuardNodeBridge.common.service_pb2 import User
from PasarGuardNodeBridge.storage import LifecycleOperation, LifecycleStatus, NodeLifecycleState

from app.nats.kv_cas import MemoryCasKv
from app.node.nats_memory import NatsNodeLifecycleCoordinator, NatsUserSyncStore, _b64_user as _b64


def _user(email: str, inbound: str = "in") -> User:
    return User(email=email, inbounds=[inbound])


@pytest.mark.asyncio
async def test_shared_queue_uses_configured_batch_budget_without_dropping_remainder(monkeypatch):
    monkeypatch.setattr("app.node.nats_memory.nats_settings.node_update_users_batch_size", 3)
    store = NatsUserSyncStore(MemoryCasKv())
    await store.enqueue_users("1", [_user(f"user-{number}") for number in range(8)])
    delivered = []
    for expected_size in (3, 3, 2):
        claimed = await store.claim_users("1", "worker", limit=2000, lease_seconds=30)
        assert len(claimed) == expected_size
        delivered.extend(item.user.email for item in claimed)
        await store.ack_users("1", [item.token for item in claimed])
    assert len(set(delivered)) == 8
    assert await store.claim_users("1", "worker", limit=2000, lease_seconds=30) == []


@pytest.mark.asyncio
async def test_user_sync_enqueue_claim_ack_is_exclusive():
    store = NatsUserSyncStore(MemoryCasKv())
    await store.enqueue_users("1", [_user("a@example.com"), _user("b@example.com")])

    first = await store.claim_users("1", "worker-a", limit=1, lease_seconds=30)
    second = await store.claim_users("1", "worker-b", limit=10, lease_seconds=30)

    assert len(first) == 1
    assert len(second) == 1
    assert {first[0].user.email, second[0].user.email} == {"a@example.com", "b@example.com"}

    await store.ack_users("1", [first[0].token])
    assert await store.claim_users("1", "worker-a", limit=10, lease_seconds=30) == []


@pytest.mark.asyncio
async def test_user_sync_latest_email_wins_and_requeue_works():
    store = NatsUserSyncStore(MemoryCasKv())
    await store.enqueue_users("1", [_user("a@example.com", "old")])
    await store.enqueue_users("1", [_user("a@example.com", "new")])

    claimed = await store.claim_users("1", "worker-a", limit=10, lease_seconds=30)
    assert len(claimed) == 1
    assert list(claimed[0].user.inbounds) == ["new"]

    await store.requeue_users("1", claimed)
    claimed_again = await store.claim_users("1", "worker-b", limit=10, lease_seconds=30)
    assert [item.user.email for item in claimed_again] == ["a@example.com"]


@pytest.mark.asyncio
async def test_user_sync_expired_claim_becomes_available():
    store = NatsUserSyncStore(MemoryCasKv())
    await store.enqueue_users("1", [_user("a@example.com")])
    await store.claim_users("1", "worker-a", limit=10, lease_seconds=0)
    await asyncio.sleep(0.01)

    claimed = await store.claim_users("1", "worker-b", limit=10, lease_seconds=30)
    assert [item.user.email for item in claimed] == ["a@example.com"]


@pytest.mark.asyncio
async def test_user_sync_enqueue_shards_per_email_key():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    users = [_user(f"user{i}@example.com") for i in range(50)]
    await store.enqueue_users("1", users)

    pending_keys = [key for key in kv._data if key.startswith("p.1.")]
    assert len(pending_keys) == 50

    claimed = await store.claim_users("1", "worker-a", limit=50, lease_seconds=30)
    assert len(claimed) == 50
    await store.clear("1")
    assert kv._data == {}


@pytest.mark.asyncio
async def test_bulk_sync_bounds_concurrent_writes_across_nodes():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    create = kv.create
    active = peak = 0

    async def slow_create(key, value):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.001)
            return await create(key, value)
        finally:
            active -= 1

    kv.create = slow_create
    users = [_user(f"user{i}") for i in range(200)]
    await asyncio.gather(*(store.enqueue_users(str(node), users) for node in range(4)))
    assert len(kv._data) == 800
    assert 1 < peak <= 32
    assert active == 0


@pytest.mark.asyncio
async def test_claim_conflict_leaves_pending_entry_unclaimed():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.enqueue_users("1", [_user("a@example.com")])
    original_update = kv.update

    async def _update(key: str, value: bytes, last: int | None = None) -> int:
        if key.startswith("p.1."):
            raise KeyWrongLastSequenceError("wrong last sequence")
        return await original_update(key, value, last=last)

    kv.update = _update  # type: ignore[method-assign]
    assert await store.claim_users("1", "worker-a", limit=10, lease_seconds=30) == []
    kv.update = original_update  # type: ignore[method-assign]
    pending = [json.loads(value) for key, (value, _) in kv._data.items() if key.startswith("p.1.")]
    assert pending == [{"email": "a@example.com", "user": pending[0]["user"]}]
    assert [item.user.email for item in await store.claim_users("1", "worker-a", limit=10, lease_seconds=30)] == [
        "a@example.com"
    ]


async def _inbounds_delivered_after(store, node, extra_claim_first: bool):
    delivered = []
    if extra_claim_first:
        newer = await store.claim_users(node, "b", 1, 30)
        delivered.extend(list(item.user.inbounds) for item in newer)
        await store.ack_users(node, [item.token for item in newer])
    remaining = await store.claim_users(node, "b", 10, 30)
    delivered.extend(list(item.user.inbounds) for item in remaining)
    await store.ack_users(node, [item.token for item in remaining])
    return delivered


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["retry_over_newer", "expired_over_newer", "retry_after_newer_acked"])
async def test_stale_claim_never_resurrects_a_newer_state(scenario):
    """An old enabled payload must not come back after a newer disable, even once the disable was acked."""
    kv = MemoryCasKv()
    first, second = NatsUserSyncStore(kv), NatsUserSyncStore(kv)
    await first.enqueue_users("1", [_user("u", "old-enabled")])
    # A live claim stays visible across the newer enqueue, so the "newer acked first"
    # interleaving requires the old lease to have lapsed (slow or dead worker).
    old = await first.claim_users("1", "a", 1, 30 if scenario == "retry_over_newer" else 0)
    await second.enqueue_users("1", [User(email="u", inbounds=[])])  # newer: disabled
    if scenario == "retry_after_newer_acked":
        delivered = await _inbounds_delivered_after(second, "1", extra_claim_first=True)
        assert delivered == [[]]
    if scenario != "expired_over_newer":
        assert await first.requeue_users("1", old) == ["u"]
    delivered = await _inbounds_delivered_after(second, "1", extra_claim_first=False)
    assert all(inbounds == [] for inbounds in delivered)
    assert not any(key.startswith("p.1.") for key in kv._data)


@pytest.mark.asyncio
async def test_ack_reports_unconfirmed_only_when_entry_vanished():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.enqueue_users("1", [_user("a"), _user("b")])
    claimed = {item.user.email: item for item in await store.claim_users("1", "a", 10, 30)}
    # a newer payload replaces the claim of "a"; "b" is removed entirely (delivered elsewhere / drained)
    await store.enqueue_users("1", [_user("a", "newer")])
    b_key = store._pending_key("1", "b")
    await kv.delete(b_key)
    assert await store.ack_users("1", [claimed["a"].token, claimed["b"].token]) == ["b"]
    remaining = await store.claim_users("1", "a", 10, 30)
    assert [(item.user.email, list(item.user.inbounds)) for item in remaining] == [("a", ["newer"])]


@pytest.mark.asyncio
async def test_refresh_marker_is_resolved_by_cas_and_never_overwrites_a_newer_enqueue():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    resolver_started = asyncio.Event()
    resolver_release = asyncio.Event()

    async def resolver(node_id, emails):
        resolver_started.set()
        await resolver_release.wait()
        return [_user(email, "database-read") for email in emails]

    store.refresh_resolver = resolver
    await store.request_refresh("1", ["u", "gone"])
    claim = asyncio.create_task(store.claim_users("1", "a", 10, 30))
    await resolver_started.wait()
    # An API update lands while the database read is in flight.
    await store.enqueue_users("1", [_user("u", "api-newer")])
    resolver_release.set()
    claimed = await claim
    assert [(item.user.email, list(item.user.inbounds)) for item in claimed] == [("gone", ["database-read"])]
    await store.ack_users("1", [item.token for item in claimed])
    again = await store.claim_users("1", "a", 10, 30)
    assert [(item.user.email, list(item.user.inbounds)) for item in again] == [("u", ["api-newer"])]


@pytest.mark.asyncio
async def test_refresh_marker_survives_resolver_failure_and_full_sync_capture():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    calls = 0

    async def failing_resolver(node_id, emails):
        nonlocal calls
        calls += 1
        raise RuntimeError("database unavailable")

    store.refresh_resolver = failing_resolver
    await store.request_refresh("1", ["u"])
    assert await store.claim_users("1", "a", 10, 30) == []
    assert calls == 1
    # A full snapshot that fails leaves the marker where it was.
    captured, active = await store.capture_queued("1")
    assert len(captured) == 1 and active == 0
    assert any(key.startswith("p.1.") for key in kv._data)
    store.refresh_resolver = AsyncMock(return_value=[_user("u", "current")])
    assert [(item.user.email, list(item.user.inbounds)) for item in await store.claim_users("1", "a", 10, 30)] == [
        ("u", ["current"])
    ]


@pytest.mark.asyncio
async def test_refresh_claimed_turns_delivery_into_marker_unless_newer_state_exists():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.enqueue_users("1", [_user("kept", "old"), _user("replaced", "old"), _user("gone", "old")])
    claimed = {item.user.email: item for item in await store.claim_users("1", "a", 10, 30)}
    await store.enqueue_users("1", [_user("replaced", "newer")])
    await kv.delete(store._pending_key("1", "gone"))
    await store.refresh_claimed("1", list(claimed.values()))
    docs = {
        json.loads(value)["email"]: json.loads(value) for key, (value, _) in kv._data.items() if key.startswith("p.1.")
    }
    assert docs["kept"] == {"email": "kept", "refresh": True}
    assert docs["gone"] == {"email": "gone", "refresh": True}
    assert "user" in docs["replaced"] and "refresh" not in docs["replaced"]
    store.refresh_resolver = AsyncMock(side_effect=lambda node, emails: [_user(email, "db") for email in emails])
    delivered = {item.user.email: list(item.user.inbounds) for item in await store.claim_users("1", "a", 10, 30)}
    assert delivered == {"kept": ["db"], "gone": ["db"], "replaced": ["newer"]}


@pytest.mark.asyncio
async def test_resolve_refresh_markers_prepares_queue_for_a_marker_unaware_rollback():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    store.refresh_resolver = AsyncMock(
        side_effect=lambda node, emails: [_user(e, "current") for e in emails if e != "gone"]
    )
    await store.request_refresh("1", ["a", "gone"])
    await store.enqueue_users("1", [_user("b", "payload")])
    assert await store.resolve_refresh_markers("1") == (2, 0)
    docs = {json.loads(v)["email"]: json.loads(v) for k, (v, _) in kv._data.items() if k.startswith("p.1.")}
    assert set(docs) == {"a", "b"} and all("user" in doc and "refresh" not in doc for doc in docs.values())
    assert await store.resolve_refresh_markers("1") == (0, 0)


@pytest.mark.asyncio
async def test_refresh_marker_without_payload_is_retired_and_removal_is_delivered():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    store.refresh_resolver = AsyncMock(return_value=[User(email="deleted", inbounds=[])])
    await store.request_refresh("1", ["deleted", "unknown"])
    claimed = await store.claim_users("1", "a", 10, 30)
    assert [(item.user.email, list(item.user.inbounds)) for item in claimed] == [("deleted", [])]
    await store.ack_users("1", [item.token for item in claimed])
    assert not any(key.startswith("p.1.") for key in kv._data)


@pytest.mark.asyncio
async def test_capture_is_non_destructive_and_retire_removes_only_captured_revisions():
    kv = MemoryCasKv()
    first, second = NatsUserSyncStore(kv), NatsUserSyncStore(kv)
    await first.enqueue_users("1", [_user("a"), _user("b"), _user("c")])
    await first.request_refresh("1", ["m"])
    in_flight = await second.claim_users("1", "other-worker", 1, 30)
    assert [item.user.email for item in in_flight] == ["a"]
    captured, active = await first.capture_queued("1")
    assert active == 1  # "a" is being delivered by another worker
    assert set(captured) == {first._pending_key("1", email) for email in ("b", "c", "m")}
    assert len([key for key in kv._data if key.startswith("p.1.")]) == 4  # nothing deleted
    # Newer state for "b" arrives after the capture: it must survive retirement.
    await second.enqueue_users("1", [_user("b", "newer")])
    assert await first.retire_captured("1", captured) == 2
    remaining = {key: json.loads(value) for key, (value, _) in kv._data.items() if key.startswith("p.1.")}
    assert {doc["email"] for doc in remaining.values()} == {"a", "b"}
    await second.ack_users("1", [item.token for item in in_flight])
    assert [list(item.user.inbounds) for item in await second.claim_users("1", "x", 10, 30)] == [["newer"]]


@pytest.mark.asyncio
async def test_capture_reads_each_unchanged_entry_once():
    kv = MemoryCasKv()
    writer, store = NatsUserSyncStore(kv), NatsUserSyncStore(kv)
    await writer.enqueue_users("1", [_user(f"u{i}") for i in range(10)])  # written by another worker
    original_get = kv.get
    reads = 0

    async def counting_get(key):
        nonlocal reads
        reads += 1
        return await original_get(key)

    kv.get = counting_get  # type: ignore[method-assign]
    first, _ = await store.capture_queued("1")
    assert reads == 10
    second, _ = await store.capture_queued("1")
    assert reads == 10 and first == second


@pytest.mark.asyncio
async def test_failed_snapshot_leaves_queue_intact_without_restore():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.enqueue_users("1", [_user("a"), _user("b")])
    captured, _ = await store.capture_queued("1")
    # No retirement happened (snapshot read or RPC failed): everything is still deliverable.
    assert {item.user.email for item in await store.claim_users("1", "a", 10, 30)} == {"a", "b"}
    assert len(captured) == 2


@pytest.mark.asyncio
async def test_full_sync_fence_is_exclusive_keeps_generation_and_expires():
    store = NatsUserSyncStore(MemoryCasKv())
    assert await store.fence_state("1") == (False, 0)
    token = await store.begin_full_sync("1", "worker-a", 30)
    assert token is not None
    assert await store.begin_full_sync("1", "worker-b", 30) is None
    assert await store.fence_state("1") == (True, 1)
    assert await store.renew_full_sync("1", token, 30) is True
    assert await store.renew_full_sync("1", "other", 30) is False
    await store.end_full_sync("1", token)
    assert await store.fence_state("1") == (False, 1)
    expired = await store.begin_full_sync("1", "worker-a", 0)
    assert expired is not None
    await asyncio.sleep(0.01)
    assert await store.fence_state("1") == (False, 2)
    # A late renewal by the original owner must not resurrect an expired fence.
    assert await store.renew_full_sync("1", expired, 30) is False
    assert await store.fence_state("1") == (False, 2)
    assert await store.begin_full_sync("1", "worker-b", 30) is not None
    assert await store.fence_state("1") == (True, 3)
    await store.clear_full_sync("1")
    assert await store.fence_state("1") == (False, 0)


@pytest.mark.asyncio
async def test_legacy_claim_is_honored_while_unexpired_then_resolved_from_current_state():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    store.refresh_resolver = AsyncMock(side_effect=lambda node, emails: [_user(email, "current") for email in emails])
    legacy_key = "c.1.deadbeef"
    payload = {"token": "t", "email": "u", "user": _b64(_user("u", "stale-legacy")), "expires_at": time.time() + 60}
    await kv.create(legacy_key, json.dumps(payload).encode())
    # Unexpired: an old worker may still be delivering; leave it and count it as active.
    assert await store.claim_users("1", "a", 10, 30) == []
    assert legacy_key in kv._data
    assert (await store.capture_queued("1"))[1] == 1
    # Expired: re-derive from the source of truth instead of replaying the stale payload.
    payload["expires_at"] = time.time() - 1
    await kv.update(legacy_key, json.dumps(payload).encode())
    original_create = kv.create

    async def failing_create(key: str, value: bytes) -> int:
        raise nats_errors.Error("transport lost")

    kv.create = failing_create  # type: ignore[method-assign]
    with pytest.raises(nats_errors.Error):
        await store.claim_users("1", "a", 10, 30)
    assert legacy_key in kv._data  # not removed while its marker could not be written
    kv.create = original_create  # type: ignore[method-assign]
    claimed = await store.claim_users("1", "a", 10, 30)
    assert [(item.user.email, list(item.user.inbounds)) for item in claimed] == [("u", ["current"])]
    assert legacy_key not in kv._data


@pytest.mark.asyncio
async def test_old_token_cannot_release_the_same_workers_newer_claim():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.enqueue_users("1", [_user("u", "v1")])
    old = await store.claim_users("1", "a", 10, 0)  # lease already expired
    await asyncio.sleep(0.01)
    newer = await store.claim_users("1", "a", 10, 30)  # same worker re-claims
    assert [item.user.email for item in newer] == ["u"] and newer[0].token != old[0].token
    await store.enqueue_users("1", [_user("u", "v2")])  # preserves the live claim
    assert await store.requeue_users("1", old) == ["u"]
    assert await store.ack_users("1", [old[0].token]) == []
    docs = [json.loads(value) for key, (value, _) in kv._data.items() if key.startswith("p.1.")]
    assert docs[0]["claim"]["id"] == newer[0].token.rsplit(".", 1)[1]
    assert await store.claim_users("1", "b", 10, 30) == []  # still owned by the live claim
    assert await store.ack_users("1", [newer[0].token]) == []  # v2 replaced it: release, not drop
    assert [list(item.user.inbounds) for item in await store.claim_users("1", "b", 10, 30)] == [["v2"]]


@pytest.mark.asyncio
async def test_enqueue_keeps_in_flight_claim_visible_until_its_owner_settles():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.enqueue_users("1", [_user("u", "v1")])
    in_flight = await store.claim_users("1", "a", 10, 30)
    await store.enqueue_users("1", [_user("u", "v2")])
    captured, active = await store.capture_queued("1")
    assert active == 1 and captured == {}
    assert await store.claim_users("1", "b", 10, 30) == []
    assert await store.ack_users("1", [item.token for item in in_flight]) == []
    captured, active = await store.capture_queued("1")
    assert active == 0 and len(captured) == 1
    assert [list(item.user.inbounds) for item in await store.claim_users("1", "b", 10, 30)] == [["v2"]]


@pytest.mark.asyncio
async def test_scans_skip_other_workers_live_claims_without_reads():
    kv = MemoryCasKv()
    first, second = NatsUserSyncStore(kv), NatsUserSyncStore(kv)
    await first.enqueue_users("1", [_user(f"u{i}") for i in range(20)])
    assert len(await first.claim_users("1", "a", 100, 30)) == 20
    original_get = kv.get
    reads = 0

    async def counting_get(key):
        nonlocal reads
        reads += 1
        return await original_get(key)

    kv.get = counting_get  # type: ignore[method-assign]
    assert await second.claim_users("1", "b", 100, 30) == []
    assert reads == 20  # one read per foreign claim to learn its lease
    assert await second.claim_users("1", "b", 100, 30) == []
    assert reads == 20  # cached until the lease expires or the entry changes
    await first.ack_users("1", [])


@pytest.mark.asyncio
async def test_lifecycle_has_active_lease_tracks_expiry():
    coordinator = NatsNodeLifecycleCoordinator(MemoryCasKv())
    assert await coordinator.has_active_lease("1") is False

    lease = await coordinator.try_acquire("1", "worker-a", LifecycleOperation.START, 30)
    assert lease is not None
    assert await coordinator.has_active_lease("1") is True
    assert await coordinator.heartbeat(lease) is True

    await coordinator.release(lease)
    assert await coordinator.has_active_lease("1") is False
    assert await coordinator.heartbeat(lease) is False

    expired = await coordinator.try_acquire("1", "worker-a", LifecycleOperation.RECONNECT, 0)
    assert expired is not None
    await asyncio.sleep(0.01)
    assert await coordinator.has_active_lease("1") is False


@pytest.mark.asyncio
async def test_lifecycle_lease_exclusive_and_epoch_fenced():
    coordinator = NatsNodeLifecycleCoordinator(MemoryCasKv())

    first = await coordinator.try_acquire("1", "worker-a", LifecycleOperation.START, 30)
    second = await coordinator.try_acquire("1", "worker-b", LifecycleOperation.START, 30)
    assert first is not None
    assert second is None

    await coordinator.release(
        first,
        state_update=NodeLifecycleState(
            desired=LifecycleStatus.HEALTHY,
            observed=LifecycleStatus.HEALTHY,
            epoch=first.epoch,
            node_version="0.2.0",
            core_version="1.0.0",
        ),
    )
    state = await coordinator.get_state("1")
    assert state.observed is LifecycleStatus.HEALTHY
    assert state.owner is None

    stale = await coordinator.try_acquire("1", "worker-a", LifecycleOperation.RECONNECT, 0)
    await asyncio.sleep(0.01)
    newer = await coordinator.try_acquire("1", "worker-b", LifecycleOperation.STOP, 30)
    assert stale is not None
    assert newer is not None

    await coordinator.update_observed("1", LifecycleStatus.BROKEN, expected_epoch=stale.epoch)
    state = await coordinator.get_state("1")
    assert state.epoch == newer.epoch
    assert state.observed is not LifecycleStatus.BROKEN
