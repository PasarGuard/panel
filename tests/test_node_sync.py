import asyncio

import pytest

from app.nats.node_rpc import encode_node_command
from app.node import sync as node_sync_module


class _FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id
        self.admin_id = None


@pytest.fixture(autouse=True)
def clear_user_sync_locks():
    """Keep process-local synchronization locks isolated between tests."""
    node_sync_module._user_sync_locks.clear()
    yield
    node_sync_module._user_sync_locks.clear()


def test_node_update_users_nats_chunks_respect_payload_limit(monkeypatch: pytest.MonkeyPatch):
    users = [{"email": f"user-{index}", "payload": "x" * 600} for index in range(5)]
    max_payload = len(encode_node_command("update_users", {"users": users[:2]}))

    monkeypatch.setattr(node_sync_module.nats_settings, "node_update_users_batch_size", 100)
    monkeypatch.setattr(node_sync_module.nats_settings, "node_command_max_payload_bytes", max_payload)

    chunks = node_sync_module._chunk_serialized_users_for_nats(users)

    assert [len(chunk) for chunk in chunks] == [2, 2, 1]
    assert all(len(encode_node_command("update_users", {"users": chunk})) <= max_payload for chunk in chunks)


@pytest.mark.asyncio
async def test_sync_users_serializes_overlapping_updates_in_dispatch_order(monkeypatch: pytest.MonkeyPatch):
    """A newer user snapshot cannot overtake an older snapshot for the same user."""
    user = _FakeUser(7)
    serialized_revisions = 0
    dispatched_revisions: list[int] = []
    first_dispatch_started = asyncio.Event()
    release_first_dispatch = asyncio.Event()

    async def fake_blocked_admins(users):
        return set()

    async def fake_serialize(users, **kwargs):
        nonlocal serialized_revisions
        serialized_revisions += 1
        return [serialized_revisions]

    async def fake_dispatch(proto_users):
        if not dispatched_revisions:
            first_dispatch_started.set()
            await release_first_dispatch.wait()
        dispatched_revisions.extend(proto_users)

    monkeypatch.setattr(node_sync_module, "_blocked_admin_ids_for_users", fake_blocked_admins)
    monkeypatch.setattr(node_sync_module, "serialize_users_for_node", fake_serialize)
    monkeypatch.setattr(node_sync_module, "_dispatch_users_update", fake_dispatch)
    first = asyncio.create_task(node_sync_module.sync_users([user], wait_for_dispatch=True))
    await first_dispatch_started.wait()
    second = asyncio.create_task(node_sync_module.sync_users([user], wait_for_dispatch=True))
    await asyncio.sleep(0)
    assert not second.done()

    release_first_dispatch.set()
    await asyncio.gather(first, second)
    assert dispatched_revisions == [1, 2]


@pytest.mark.asyncio
async def test_cancelled_lock_acquisition_releases_already_acquired_locks():
    """Cancellation while waiting for a later user must not leak earlier locks."""
    blocked_lock = node_sync_module._user_sync_locks.setdefault(2, asyncio.Lock())
    await blocked_lock.acquire()

    acquisition = asyncio.create_task(node_sync_module._acquire_user_sync_locks([1, 2]))
    for _ in range(10):
        first_lock = node_sync_module._user_sync_locks.get(1)
        if first_lock is not None and first_lock.locked():
            break
        await asyncio.sleep(0)
    assert first_lock is not None and first_lock.locked()

    acquisition.cancel()
    with pytest.raises(asyncio.CancelledError):
        await acquisition

    assert not node_sync_module._user_sync_locks[1].locked()
    assert blocked_lock.locked()
    blocked_lock.release()


@pytest.mark.asyncio
async def test_sync_users_refreshes_tags_after_acquiring_user_lock(monkeypatch: pytest.MonkeyPatch):
    """A waiting group sync must serialize access loaded after it wins the user lock."""
    user = _FakeUser(7)
    blocker = node_sync_module._user_sync_locks.setdefault(user.id, asyncio.Lock())
    await blocker.acquire()
    serialized_tags: list[dict[int, set[str]]] = []

    async def fake_blocked_admins(users):
        return set()

    async def fake_load_current_tags(user_ids):
        return {user.id: {"fresh-inbound"}}

    async def fake_serialize(users, **kwargs):
        serialized_tags.append(kwargs["inbound_tags_by_user"])
        return []

    async def fake_dispatch(proto_users):
        return None

    monkeypatch.setattr(node_sync_module, "_blocked_admin_ids_for_users", fake_blocked_admins)
    monkeypatch.setattr(node_sync_module, "_load_current_inbound_tags", fake_load_current_tags)
    monkeypatch.setattr(node_sync_module, "serialize_users_for_node", fake_serialize)
    monkeypatch.setattr(node_sync_module, "_dispatch_users_update", fake_dispatch)

    sync_task = asyncio.create_task(
        node_sync_module.sync_users(
            [user],
            inbound_tags_by_user={user.id: {"stale-inbound"}},
            refresh_inbound_tags=True,
            wait_for_dispatch=True,
        )
    )
    await asyncio.sleep(0)
    assert not sync_task.done()

    blocker.release()
    await sync_task

    assert serialized_tags == [{user.id: {"fresh-inbound"}}]
