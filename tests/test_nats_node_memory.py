"""CAS semantics for NATS-backed bridge user-sync + lifecycle memory."""

import asyncio

import pytest
from PasarGuardNodeBridge.common.service_pb2 import User
from PasarGuardNodeBridge.storage import LifecycleOperation, LifecycleStatus, NodeLifecycleState

from app.nats.kv_cas import MemoryCasKv
from app.node.nats_memory import NatsNodeLifecycleCoordinator, NatsUserSyncStore


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
