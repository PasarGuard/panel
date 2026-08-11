"""CAS semantics for NATS-backed bridge user-sync + lifecycle memory."""

import asyncio
import json

import pytest
from PasarGuardNodeBridge.common.service_pb2 import User
from PasarGuardNodeBridge.storage import LifecycleOperation, LifecycleStatus, NodeLifecycleState

from app.nats.kv_cas import MemoryCasKv
from app.node import nats_memory
from app.node.nats_memory import (
    ClaimedUser,
    NatsNodeLifecycleCoordinator,
    NatsUserSyncStore,
    UserRevocationConflictError,
    UserSyncLease,
    UserSyncLeaseLostError,
)


class BlockingCreateKv(MemoryCasKv):
    """Deterministic CAS race: pause one create for the selected key prefix."""

    def __init__(self, prefix: str):
        super().__init__()
        self.prefix = prefix
        self.started = asyncio.Event()
        self.proceed = asyncio.Event()
        self.armed = True

    async def create(self, key: str, value: bytes) -> int:
        if self.armed and key.startswith(self.prefix):
            self.armed = False
            self.started.set()
            await self.proceed.wait()
        return await super().create(key, value)


def _json_doc(kv: MemoryCasKv, key: str) -> dict:
    return json.loads(kv._data[key][0])


def _user(email: str, inbound: str = "in") -> User:
    return User(email=email, inbounds=[inbound])


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
async def test_next_claim_delay_tracks_pending_claimed_and_fenced_work(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(nats_memory.time, "time", lambda: now[0])
    store = NatsUserSyncStore(MemoryCasKv())
    assert await store.next_claim_delay("1") is None

    await store.enqueue_users("1", [_user("a@example.com")])
    assert await store.next_claim_delay("1") == 0.0
    await store.claim_users("1", "worker-a", limit=1, lease_seconds=5)
    assert await store.next_claim_delay("1") == 5.0

    await store.begin_user_revocation("1", ["a@example.com"], "revoke-a")
    assert await store.next_claim_delay("1") is None


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
async def test_clear_only_flushes_queue_and_preserves_revocation_safety_state():
    store = NatsUserSyncStore(MemoryCasKv())
    await store.begin_user_revocation("1", ["a@example.com"], "revoke-a")
    authorized = await store.acquire_user_sync_lease(
        "1",
        "worker",
        ["a@example.com"],
        30,
        revocation_id="revoke-a",
    )

    await store.clear("1")

    assert await store.heartbeat_user_sync_lease(authorized) is True
    ordinary = await store.acquire_user_sync_lease("1", "worker", ["a@example.com"], 30)
    assert ordinary.token == ""
    await store.release_user_sync_lease(authorized)

    await store.purge_node("1")
    after_removal = await store.acquire_user_sync_lease("1", "worker", ["a@example.com"], 30)
    assert after_removal.token
    await store.release_user_sync_lease(after_removal)


@pytest.mark.asyncio
async def test_claim_cleans_up_claimed_key_when_pending_delete_fails():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.enqueue_users("1", [_user("a@example.com")])

    original_delete = kv.delete

    async def _delete(key: str, last: int | None = None) -> bool:
        if key.startswith("p.1."):
            raise RuntimeError("pending delete race")
        return await original_delete(key, last=last)

    kv.delete = _delete  # type: ignore[method-assign]

    claimed = await store.claim_users("1", "worker-a", limit=10, lease_seconds=30)
    assert claimed == []
    assert not any(key.startswith("c.1.") for key in kv._data)
    assert any(key.startswith("p.1.") for key in kv._data)


@pytest.mark.asyncio
async def test_revocation_purges_queue_and_abort_advances_generation():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.enqueue_users("1", [_user("a@example.com")])
    claimed = await store.claim_users("1", "worker-a", limit=10, lease_seconds=30)
    assert claimed[0].generation == 0

    await store.begin_user_revocation("1", ["a@example.com"], "revoke-a")
    assert not any(key.startswith(("p.1.", "c.1.")) for key in kv._data)

    await store.enqueue_users("1", [_user("a@example.com", "blocked")])
    assert await store.claim_users("1", "worker-b", limit=10, lease_seconds=30) == []

    await store.abort_user_revocation("1", ["a@example.com"], "revoke-a")
    await store.enqueue_users("1", [_user("a@example.com", "restored")])
    fresh = await store.claim_users("1", "worker-b", limit=10, lease_seconds=30)
    assert len(fresh) == 1
    assert fresh[0].generation == 1
    assert list(fresh[0].user.inbounds) == ["restored"]


@pytest.mark.asyncio
async def test_stale_claim_cannot_requeue_or_acquire_after_fast_abort():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.enqueue_users("1", [_user("a@example.com")])
    stale = (await store.claim_users("1", "worker-a", limit=1, lease_seconds=30))[0]

    await store.begin_user_revocation("1", ["a@example.com"], "revoke-a")
    await store.abort_user_revocation("1", ["a@example.com"], "revoke-a")

    lease = await store.acquire_user_sync_lease(
        "1",
        "worker-a",
        ["a@example.com"],
        30,
        expected_generations={"a@example.com": stale.generation},
    )
    assert lease.token == ""

    await store.requeue_users("1", [stale])
    assert await store.claim_users("1", "worker-b", limit=1, lease_seconds=30) == []


@pytest.mark.asyncio
async def test_overlapping_revocation_fails_fast_and_finalize_is_permanent():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    key = "a@example.com"

    await store.begin_user_revocation("1", [key], "revoke-a")
    with pytest.raises(UserRevocationConflictError):
        await store.begin_user_revocation("1", [key], "revoke-b")
    await store.abort_user_revocation("1", [key], "revoke-a")

    await store.begin_user_revocation("1", [key], "revoke-b")
    await store.finalize_user_revocation("1", [key], "revoke-b")
    await store.abort_user_revocation("1", [key], "revoke-b")
    await store.enqueue_users("1", [_user(key)])
    lease = await store.acquire_user_sync_lease("1", "worker", [key], 30)
    assert lease.token == ""
    assert await store.claim_users("1", "worker", 1, 30) == []

    barrier_key = next(key for key in kv._data if key.startswith("b.1."))
    assert _json_doc(kv, barrier_key)["permanent"] is True
    assert _json_doc(kv, barrier_key)["active_owner"] is None


@pytest.mark.asyncio
async def test_bulk_conflict_unwinds_keys_acquired_before_the_conflict():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.enqueue_users("1", [_user("a@example.com", "queued")])
    claimed = await store.claim_users("1", "worker-a", 1, 30)
    assert claimed[0].generation == 0
    await store.begin_user_revocation("1", ["b@example.com"], "revoke-b")

    with pytest.raises(UserRevocationConflictError):
        await store.begin_user_revocation(
            "1",
            ["a@example.com", "b@example.com"],
            "revoke-a",
        )

    # The all-key conflict is a strict no-op for a: its generation and claimed
    # authoritative payload remain valid instead of being silently discarded.
    lease = await store.acquire_user_sync_lease(
        "1",
        "worker",
        ["a@example.com"],
        30,
        expected_generations={"a@example.com": claimed[0].generation},
    )
    assert lease.token
    await store.release_user_sync_lease(lease)
    await store.requeue_users("1", claimed)
    requeued = await store.claim_users("1", "worker-b", 1, 30)
    assert list(requeued[0].user.inbounds) == ["queued"]


@pytest.mark.asyncio
@pytest.mark.parametrize("close_method", ["abort_user_revocation", "finalize_user_revocation"])
async def test_partial_close_cas_failure_reopens_every_marked_key(monkeypatch, close_method):
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    keys = ["a@example.com", "b@example.com"]
    await store.begin_user_revocation("1", keys, "revoke-a")
    original_cas = nats_memory.kv_cas_json
    blocked_key = store._barrier_key("1", "b@example.com")

    async def fail_second_closing(kv_arg, key, value, revision):
        if key == blocked_key and value.get("closing") is True:
            return False
        return await original_cas(kv_arg, key, value, revision)

    monkeypatch.setattr(nats_memory, "kv_cas_json", fail_second_closing)
    with pytest.raises(RuntimeError, match="after CAS retries"):
        await getattr(store, close_method)("1", keys, "revoke-a")

    for user_key in keys:
        barrier, _ = await store._get_barrier("1", user_key)
        assert barrier["active_owner"] == "revoke-a"
        assert barrier["closing"] is False

    owner = await store.acquire_user_sync_lease(
        "1",
        "worker",
        keys,
        30,
        revocation_id="revoke-a",
    )
    assert owner.user_keys == tuple(keys)
    await store.release_user_sync_lease(owner)


@pytest.mark.asyncio
async def test_partial_begin_cas_failure_restores_generations_and_claims(monkeypatch):
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    keys = ["a@example.com", "b@example.com"]
    await store.enqueue_users("1", [_user(keys[0], "queued")])
    claimed = await store.claim_users("1", "worker-a", 1, 30)
    original_cas = nats_memory.kv_cas_json
    blocked_key = store._barrier_key("1", keys[1])

    async def fail_second_fence(kv_arg, key, value, revision):
        if key == blocked_key and value.get("active_owner") == "delete":
            return False
        return await original_cas(kv_arg, key, value, revision)

    monkeypatch.setattr(nats_memory, "kv_cas_json", fail_second_fence)
    with pytest.raises(RuntimeError, match="after CAS retries"):
        await store.begin_user_revocation("1", keys, "delete")

    for user_key in keys:
        barrier, _ = await store._get_barrier("1", user_key)
        assert barrier["generation"] == 0
        assert barrier["active_owner"] is None
    lease = await store.acquire_user_sync_lease(
        "1",
        "worker-b",
        [keys[0]],
        30,
        expected_generations={keys[0]: claimed[0].generation},
    )
    assert lease.token
    await store.release_user_sync_lease(lease)
    await store.requeue_users("1", claimed)
    assert (await store.claim_users("1", "worker-b", 1, 30))[0].user.email == keys[0]


@pytest.mark.asyncio
async def test_begin_reports_already_finalized_keys_without_reopening_them():
    store = NatsUserSyncStore(MemoryCasKv())
    await store.begin_user_revocation("1", ["a@example.com"], "revoke-a")
    await store.finalize_user_revocation("1", ["a@example.com"], "revoke-a")

    result = await store.begin_user_revocation(
        "1",
        ["a@example.com", "b@example.com"],
        "revoke-b",
    )

    assert result.active_user_keys == ("b@example.com",)
    assert result.finalized_user_keys == ("a@example.com",)


@pytest.mark.asyncio
async def test_begin_waits_for_intersecting_execution_lease():
    store = NatsUserSyncStore(MemoryCasKv())
    lease = await store.acquire_user_sync_lease("1", "worker-a", ["a@example.com", "b@example.com"], 30)
    assert lease.token

    begin = asyncio.create_task(store.begin_user_revocation("1", ["b@example.com"], "revoke-a"))
    for _ in range(5):
        await asyncio.sleep(0)
    assert not begin.done()

    await store.release_user_sync_lease(lease)
    await asyncio.wait_for(begin, timeout=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("close_method", ["abort_user_revocation", "finalize_user_revocation"])
async def test_revocation_close_blocks_new_admission_and_waits_authorized_lease(close_method):
    store = NatsUserSyncStore(MemoryCasKv())
    key = "a@example.com"
    await store.begin_user_revocation("1", [key], "revoke-a")
    authorized = await store.acquire_user_sync_lease(
        "1",
        "worker-a",
        [key],
        30,
        revocation_id="revoke-a",
    )

    close = asyncio.create_task(getattr(store, close_method)("1", [key], "revoke-a"))
    for _ in range(5):
        await asyncio.sleep(0)
    assert not close.done()
    late_authorized = await store.acquire_user_sync_lease(
        "1",
        "worker-b",
        [key],
        30,
        revocation_id="revoke-a",
    )
    assert late_authorized.token == ""

    await store.release_user_sync_lease(authorized)
    await asyncio.wait_for(close, timeout=1)
    ordinary = await store.acquire_user_sync_lease("1", "worker-b", [key], 30)
    if close_method == "abort_user_revocation":
        assert ordinary.token
        await store.release_user_sync_lease(ordinary)
    else:
        assert ordinary.token == ""


@pytest.mark.asyncio
async def test_execution_lease_on_other_node_does_not_block_begin():
    store = NatsUserSyncStore(MemoryCasKv())
    lease = await store.acquire_user_sync_lease("1", "worker-a", ["a@example.com"], 30)
    assert lease.token

    result = await store.begin_user_revocation("2", ["a@example.com"], "revoke-a")

    assert result.active_user_keys == ("a@example.com",)
    await store.release_user_sync_lease(lease)


@pytest.mark.asyncio
@pytest.mark.parametrize("close_method", ["abort_user_revocation", "finalize_user_revocation"])
async def test_failed_close_reopens_only_owner_admission_for_authoritative_reconcile(
    monkeypatch,
    close_method,
):
    now = [100.0]
    monkeypatch.setattr(nats_memory.time, "time", lambda: now[0])
    store = NatsUserSyncStore(MemoryCasKv())
    key = "a@example.com"
    await store.begin_user_revocation("1", [key], "revoke-a")
    unknown = await store.acquire_user_sync_lease(
        "1",
        "worker-a",
        [key],
        5,
        revocation_id="revoke-a",
    )
    now[0] = 106.0

    with pytest.raises(UserSyncLeaseLostError):
        await getattr(store, close_method)("1", [key], "revoke-a")

    ordinary = await store.acquire_user_sync_lease("1", "worker-b", [key], 30)
    owner = await store.acquire_user_sync_lease(
        "1",
        "worker-b",
        [key],
        30,
        revocation_id="revoke-a",
    )
    assert ordinary.token == ""
    assert owner.token
    await store.release_user_sync_lease(owner)
    await store.release_user_sync_lease(unknown)
    await getattr(store, close_method)("1", [key], "revoke-a")


@pytest.mark.asyncio
async def test_expired_execution_lease_fails_begin_closed_until_reconciled(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(nats_memory.time, "time", lambda: now[0])
    store = NatsUserSyncStore(MemoryCasKv())
    lease = await store.acquire_user_sync_lease("1", "worker-a", ["a@example.com"], 5)
    assert lease.token
    now[0] = 102.0
    assert await store.heartbeat_user_sync_lease(lease) is True
    now[0] = 108.0

    with pytest.raises(UserSyncLeaseLostError):
        await store.begin_user_revocation("1", ["a@example.com"], "revoke-a")

    # begin installed the fence before detecting the unknown remote outcome.
    await store.enqueue_users("1", [_user("a@example.com", "blocked")])
    assert await store.claim_users("1", "worker-b", 1, 30) == []

    await store.release_user_sync_lease(lease)
    await store.abort_user_revocation("1", ["a@example.com"], "revoke-a")
    await store.enqueue_users("1", [_user("a@example.com", "restored")])
    assert len(await store.claim_users("1", "worker-b", 1, 30)) == 1


@pytest.mark.asyncio
async def test_authoritative_reconciliation_replaces_crashed_execution_lease(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(nats_memory.time, "time", lambda: now[0])
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    lost = await store.acquire_user_sync_lease("1", "dead-worker", ["a@example.com"], 5)
    now[0] = 106.0
    await store.set_authoritative_reconciliation_membership(
        "1", "recovery-worker", ["a@example.com", "b@example.com"]
    )

    recovery = await store.acquire_user_sync_reconciliation_lease(
        "1", "recovery-worker", ["a@example.com", "b@example.com"], 30
    )

    assert recovery.lease.covers_all_users is True
    assert recovery.included_user_keys == ("a@example.com", "b@example.com")
    assert not any(lost.token in json.loads(raw).get("token", "") for raw, _ in kv._data.values())
    await store.release_user_sync_lease(recovery.lease)


@pytest.mark.asyncio
async def test_expired_revocation_metadata_lock_requires_authoritative_recovery(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(nats_memory.time, "time", lambda: now[0])
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    assert await nats_memory.kv_cas_json(
        kv,
        store._revocation_lock_key("1"),
        {"token": "dead-worker", "expires_at": 99.0},
        0,
    )

    with pytest.raises(UserRevocationConflictError):
        await store.begin_user_revocation("1", ["a@example.com"], "revoke-a")

    await store.set_authoritative_reconciliation_membership("1", "recovery", ["a@example.com"])
    recovery = await store.acquire_user_sync_reconciliation_lease(
        "1", "recovery", ["a@example.com"], 30
    )
    await store.release_user_sync_lease(recovery.lease)
    result = await store.begin_user_revocation("1", ["a@example.com"], "revoke-a")

    assert result.active_user_keys == ("a@example.com",)


@pytest.mark.asyncio
async def test_paused_expired_metadata_owner_is_not_stolen_and_fails_closed(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(nats_memory.time, "time", lambda: now[0])
    store = NatsUserSyncStore(MemoryCasKv())

    with pytest.raises(UserSyncLeaseLostError):
        async with store._revocation_lock("1", ["a@example.com"]) as assert_owned:
            now[0] += nats_memory._REVOCATION_METADATA_LEASE_SECONDS + 1
            with pytest.raises(UserRevocationConflictError):
                await store.begin_user_revocation("1", ["a@example.com"], "other-owner")
            await assert_owned()


@pytest.mark.asyncio
async def test_only_matching_revocation_owner_can_acquire_fenced_direct_sync_lease():
    store = NatsUserSyncStore(MemoryCasKv())
    key = "a@example.com"
    await store.begin_user_revocation("1", [key], "revoke-a")

    ordinary = await store.acquire_user_sync_lease("1", "worker", [key], 30)
    wrong_owner = await store.acquire_user_sync_lease("1", "worker", [key], 30, revocation_id="revoke-b")
    authorized = await store.acquire_user_sync_lease("1", "worker", [key], 30, revocation_id="revoke-a")

    assert ordinary.token == ""
    assert wrong_owner.token == ""
    assert authorized.token
    await store.release_user_sync_lease(authorized)


@pytest.mark.asyncio
async def test_startup_lease_is_node_wide_filters_finalized_and_blocks_new_writes():
    store = NatsUserSyncStore(MemoryCasKv())
    await store.begin_user_revocation("1", ["deleted@example.com"], "delete")
    await store.finalize_user_revocation("1", ["deleted@example.com"], "delete")

    startup = await store.acquire_startup_user_sync_lease(
        "1",
        "starter",
        ["active@example.com", "deleted@example.com"],
        30,
    )

    assert startup.lease.token
    assert startup.lease.covers_all_users is True
    assert startup.included_user_keys == ("active@example.com",)
    ordinary = await store.acquire_user_sync_lease("1", "worker", ["active@example.com"], 30)
    assert ordinary.token == ""
    await store.release_user_sync_lease(startup.lease)


@pytest.mark.asyncio
async def test_startup_waits_for_prior_write_and_then_begin_waits_for_startup():
    store = NatsUserSyncStore(MemoryCasKv())
    ordinary = await store.acquire_user_sync_lease("1", "worker", ["a@example.com"], 30)
    startup_task = asyncio.create_task(store.acquire_startup_user_sync_lease("1", "starter", ["a@example.com"], 30))
    for _ in range(5):
        await asyncio.sleep(0)
    assert not startup_task.done()

    await store.release_user_sync_lease(ordinary)
    startup = await asyncio.wait_for(startup_task, timeout=1)
    begin = asyncio.create_task(store.begin_user_revocation("1", ["a@example.com"], "delete"))
    for _ in range(5):
        await asyncio.sleep(0)
    assert not begin.done()

    await store.release_user_sync_lease(startup.lease)
    await asyncio.wait_for(begin, timeout=1)


@pytest.mark.asyncio
async def test_ordinary_lease_losing_startup_create_race_self_rejects():
    kv = BlockingCreateKv("x.1.")
    store = NatsUserSyncStore(kv)
    ordinary_task = asyncio.create_task(store.acquire_user_sync_lease("1", "worker", ["a@example.com"], 30))
    await kv.started.wait()

    startup = await store.acquire_startup_user_sync_lease(
        "1",
        "starter",
        ["a@example.com"],
        30,
    )
    kv.proceed.set()
    ordinary = await asyncio.wait_for(ordinary_task, timeout=1)

    assert ordinary.token == ""
    assert startup.lease.token
    await store.release_user_sync_lease(startup.lease)


@pytest.mark.asyncio
async def test_startup_waiting_on_provisional_owner_does_not_block_authorized_restore():
    store = NatsUserSyncStore(MemoryCasKv())
    await store.begin_user_revocation("1", ["a@example.com"], "delete")
    startup_task = asyncio.create_task(store.acquire_startup_user_sync_lease("1", "starter", ["a@example.com"], 30))
    for _ in range(5):
        await asyncio.sleep(0)
    assert not startup_task.done()

    restore = await store.acquire_user_sync_lease(
        "1",
        "worker",
        ["a@example.com"],
        30,
        revocation_id="delete",
    )
    assert restore.token
    await store.release_user_sync_lease(restore)
    await store.abort_user_revocation("1", ["a@example.com"], "delete")

    startup = await asyncio.wait_for(startup_task, timeout=1)
    assert startup.included_user_keys == ("a@example.com",)
    await store.release_user_sync_lease(startup.lease)


@pytest.mark.asyncio
async def test_retain_user_sync_lease_keys_is_atomic_and_preserves_token():
    store = NatsUserSyncStore(MemoryCasKv())
    lease = await store.acquire_user_sync_lease(
        "1",
        "worker",
        ["known@example.com", "unknown@example.com"],
        30,
    )

    narrowed = await store.retain_user_sync_lease_keys(lease, ["unknown@example.com"])

    assert narrowed.token == lease.token
    assert narrowed.user_keys == ("unknown@example.com",)
    assert narrowed.epoch == lease.epoch
    assert await store.heartbeat_user_sync_lease(lease) is False
    assert await store.heartbeat_user_sync_lease(narrowed) is True
    await store.release_user_sync_lease(narrowed)


@pytest.mark.asyncio
async def test_user_sync_epochs_are_unique_and_monotonic_across_workers():
    store = NatsUserSyncStore(MemoryCasKv())
    leases = await asyncio.gather(
        *(
            store.acquire_user_sync_lease(
                "1",
                f"worker-{index}",
                [f"user-{index}@example.com"],
                30,
            )
            for index in range(16)
        )
    )

    epochs = sorted(lease.epoch for lease in leases)
    assert epochs == list(range(1, 17))
    await asyncio.gather(*(store.release_user_sync_lease(lease) for lease in leases))


@pytest.mark.asyncio
async def test_user_sync_epoch_handshake_advances_floor_under_concurrency():
    store = NatsUserSyncStore(MemoryCasKv())
    await asyncio.gather(
        store.advance_user_sync_epoch("1", 50),
        store.advance_user_sync_epoch("1", 75),
        store.advance_user_sync_epoch("1", 60),
    )

    lease = await store.acquire_user_sync_lease("1", "worker", ["a@example.com"], 30)
    assert lease.epoch == 76
    await store.release_user_sync_lease(lease)


@pytest.mark.asyncio
async def test_forged_execution_lease_cannot_heartbeat_or_release_owner():
    store = NatsUserSyncStore(MemoryCasKv())
    lease = await store.acquire_user_sync_lease("1", "worker-a", ["a@example.com"], 30)
    forged = UserSyncLease(
        node_id=lease.node_id,
        worker_id="worker-b",
        token=lease.token,
        user_keys=lease.user_keys,
        generations=lease.generations,
        lease_seconds=lease.lease_seconds,
    )

    assert await store.heartbeat_user_sync_lease(forged) is False
    await store.release_user_sync_lease(forged)
    assert await store.heartbeat_user_sync_lease(lease) is True
    await store.release_user_sync_lease(lease)


@pytest.mark.asyncio
async def test_enqueue_racing_begin_cannot_leave_stale_pending_work():
    kv = BlockingCreateKv("p.1.")
    store = NatsUserSyncStore(kv)

    enqueue = asyncio.create_task(store.enqueue_users("1", [_user("a@example.com")]))
    await kv.started.wait()
    await store.begin_user_revocation("1", ["a@example.com"], "revoke-a")
    kv.proceed.set()
    await enqueue

    assert not any(key.startswith("p.1.") for key in kv._data)


@pytest.mark.asyncio
async def test_lease_create_racing_begin_is_rejected_after_fence():
    kv = BlockingCreateKv("x.1.")
    store = NatsUserSyncStore(kv)

    acquire = asyncio.create_task(store.acquire_user_sync_lease("1", "worker-a", ["a@example.com"], 30))
    await kv.started.wait()
    await store.begin_user_revocation("1", ["a@example.com"], "revoke-a")
    kv.proceed.set()
    lease = await acquire

    assert lease.token == ""
    assert not any(key.startswith("x.1.") for key in kv._data)


@pytest.mark.asyncio
async def test_requeue_requires_owned_claim_and_matching_generation():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.enqueue_users("1", [_user("a@example.com")])
    claim = (await store.claim_users("1", "worker-a", 1, 30))[0]

    forged = ClaimedUser(token=claim.token, user=_user("other@example.com"), generation=claim.generation)
    await store.requeue_users("1", [forged])
    assert not any(key.startswith("p.1.") for key in kv._data)
    assert any(key.startswith("c.1.") for key in kv._data)

    wrong_generation = ClaimedUser(token=claim.token, user=claim.user, generation=claim.generation + 1)
    await store.requeue_users("1", [wrong_generation])
    assert not any(key.startswith("p.1.") for key in kv._data)
    assert any(key.startswith("c.1.") for key in kv._data)


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
    assert await coordinator.try_acquire("1", "worker-b", LifecycleOperation.STOP, 30) is None
    assert await coordinator.reconcile("1", LifecycleStatus.HEALTHY) is True
    replacement = await coordinator.try_acquire("1", "worker-b", LifecycleOperation.STOP, 30)
    assert replacement is not None


@pytest.mark.asyncio
async def test_lifecycle_reconcile_rejects_live_lease():
    coordinator = NatsNodeLifecycleCoordinator(MemoryCasKv())
    lease = await coordinator.try_acquire("1", "worker-a", LifecycleOperation.START, 30)
    assert lease is not None
    assert await coordinator.reconcile("1", LifecycleStatus.HEALTHY) is False
    assert await coordinator.try_acquire("1", "worker-b", LifecycleOperation.STOP, 30) is None


@pytest.mark.asyncio
async def test_authoritative_reconcile_resolves_crash_after_db_commit_barriers():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.begin_user_revocation("1", ["present", "deleted"], "delete-both")
    assert await store.needs_authoritative_recovery("1") is True

    # Simulate a full worker/process restart: only persisted KV survives.
    restarted_store = NatsUserSyncStore(kv)
    await restarted_store.set_authoritative_reconciliation_membership("1", "recovery-worker", ["present"])

    recovery = await restarted_store.acquire_user_sync_reconciliation_lease(
        # The row exists globally but is not assigned to this node's core.
        "1", "recovery-worker", [], 30
    )

    assert recovery.included_user_keys == ()
    present, _ = await restarted_store._get_barrier("1", "present")
    deleted, _ = await restarted_store._get_barrier("1", "deleted")
    assert present["active_owner"] is None
    assert present["closing"] is False
    assert present["permanent"] is False
    assert deleted["active_owner"] is None
    assert deleted["closing"] is False
    assert deleted["permanent"] is True
    assert recovery.lease.covers_all_users is True
    assert recovery.lease.epoch > 0
    assert await restarted_store.needs_authoritative_recovery("1") is False
    await restarted_store.release_user_sync_lease(recovery.lease)


@pytest.mark.asyncio
@pytest.mark.parametrize("close_method", ["abort_user_revocation", "finalize_user_revocation"])
async def test_idempotent_close_without_affected_keys_ignores_unrelated_wildcard(close_method):
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    await store.set_authoritative_reconciliation_membership("1", "startup", ["other"])
    wildcard = await store.acquire_user_sync_reconciliation_lease("1", "startup", ["other"], 30)

    await asyncio.wait_for(
        getattr(store, close_method)("1", ["missing"], "already-closed"),
        timeout=0.1,
    )

    await store.release_user_sync_lease(wildcard.lease)


@pytest.mark.asyncio
async def test_purge_node_removes_epoch_fence_too():
    kv = MemoryCasKv()
    store = NatsUserSyncStore(kv)
    lease = await store.acquire_user_sync_lease("7", "worker", ["user"], 30)
    await store.release_user_sync_lease(lease)
    assert "e.7" in kv._data

    await store.purge_node("7")

    assert not any(key == "e.7" or key.startswith(("p.7.", "c.7.", "b.7.", "x.7.")) for key in kv._data)


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
    assert newer is None

    assert await coordinator.reconcile("1", LifecycleStatus.HEALTHY) is True
    newer = await coordinator.try_acquire("1", "worker-b", LifecycleOperation.STOP, 30)
    assert newer is not None

    await coordinator.update_observed("1", LifecycleStatus.BROKEN, expected_epoch=stale.epoch)
    state = await coordinator.get_state("1")
    assert state.epoch == newer.epoch
    assert state.observed is not LifecycleStatus.BROKEN


@pytest.mark.asyncio
async def test_deleted_lifecycle_namespace_permanently_rejects_start_but_allows_stop():
    coordinator = NatsNodeLifecycleCoordinator(MemoryCasKv())

    await coordinator.mark_deleted("stable-bridge-id")

    assert await coordinator.is_deleted("stable-bridge-id") is True
    assert (
        await coordinator.try_acquire(
            "stable-bridge-id", "late-worker", LifecycleOperation.START, 30
        )
        is None
    )
    stop = await coordinator.try_acquire(
        "stable-bridge-id", "cleanup-worker", LifecycleOperation.STOP, 30
    )
    assert stop is not None
