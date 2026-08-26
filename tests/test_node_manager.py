from unittest.mock import AsyncMock, MagicMock

import pytest

from app.node import NodeManager


@pytest.mark.asyncio
async def test_update_node_can_replace_local_controller_without_remote_stop(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    old_node = object()
    new_node = object()
    db_node = MagicMock(id=19)
    manager._nodes[19] = old_node

    monkeypatch.setattr("app.node.ensure_bridge_memory", AsyncMock())
    monkeypatch.setattr(manager, "_create_node_kwargs", MagicMock(return_value={}))
    monkeypatch.setattr("app.node.create_node", MagicMock(return_value=new_node))
    shutdown = AsyncMock()
    monkeypatch.setattr(manager, "_shutdown_node", shutdown)

    result = await manager.update_node(db_node, remote_stop=False)

    assert result is new_node
    assert manager._nodes[19] is new_node
    shutdown.assert_awaited_once_with(old_node, remote_stop=False)


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
