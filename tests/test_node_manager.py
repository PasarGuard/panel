import asyncio

import pytest

from app.node import NodeManager


@pytest.mark.asyncio
async def test_node_manager_bulk_user_sync_uses_bounded_chunked_batches(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    users = [object() for _ in range(5)]

    class FakeNode:
        def __init__(self):
            self.calls: list[tuple[int, int, bool]] = []

        async def _supports_chunked_sync(self):
            return True, "0.5.2"

        async def sync_users_chunked(self, batch, chunk_size, flush_pending):
            self.calls.append((len(batch), chunk_size, flush_pending))
            return []

    fake_node = FakeNode()
    monkeypatch.setattr("app.node.nats_settings.node_update_users_batch_size", 2)

    await manager._sync_users_to_node(1, fake_node, users)

    assert fake_node.calls == [(2, 2, False), (2, 2, False), (1, 1, False)]


@pytest.mark.asyncio
async def test_node_manager_bulk_user_sync_falls_back_when_chunked_is_not_supported(
    monkeypatch: pytest.MonkeyPatch,
):
    manager = NodeManager()
    users = [object() for _ in range(3)]

    class FakeNode:
        def __init__(self):
            self.batch_calls: list[int] = []

        async def _supports_chunked_sync(self):
            return False, "0.1.0"

        async def _sync_batch_users(self, batch):
            self.batch_calls.append(len(batch))
            return []

    fake_node = FakeNode()
    monkeypatch.setattr("app.node.nats_settings.node_update_users_batch_size", 2)

    await manager._sync_users_to_node(1, fake_node, users)

    assert fake_node.batch_calls == [2, 1]


@pytest.mark.asyncio
async def test_node_manager_update_users_waits_for_dispatch(monkeypatch: pytest.MonkeyPatch):
    """A caller waiting for a batch must not return before the node work finishes."""
    manager = NodeManager()
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_update_users(users):
        started.set()
        await release.wait()

    monkeypatch.setattr(manager, "_update_users", fake_update_users)
    update_task = asyncio.create_task(manager.update_users([object()]))

    await started.wait()
    assert not update_task.done()
    release.set()
    await update_task
