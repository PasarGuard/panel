import pytest

from app.db.models import Node
from app.node import NodeManager


class _FakePGNode:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.set_health_calls = 0
        self.stop_calls = 0

    async def set_health(self, health):
        self.set_health_calls += 1

    async def stop(self, timeout=None):
        self.stop_calls += 1


def _make_node(node_id: int, **overrides) -> Node:
    defaults = {
        "name": "n1",
        "address": "10.0.0.1",
        "port": 1000,
        "api_port": 1001,
        "server_ca": "ca",
        "api_key": "key",
        "core_config_id": None,
    }
    defaults.update(overrides)
    node = Node(**defaults)
    node.id = node_id
    return node


@pytest.mark.asyncio
async def test_update_node_reuses_object_and_skips_remote_stop_when_unchanged(monkeypatch: pytest.MonkeyPatch):
    """A reconnect attempt (e.g. the health-check watchdog) with no config change must not
    kill the remote backend — that used to defeat attach-if-already-running and turn a
    transient health-check false negative into a permanent Start/Stop restart loop."""
    manager = NodeManager()

    monkeypatch.setattr("app.node.ensure_bridge_memory", lambda: _AwaitableNone())
    monkeypatch.setattr("app.node.get_bridge_memory", lambda: (None, None, None))
    monkeypatch.setattr("app.node.create_node", lambda **kwargs: _FakePGNode(**kwargs))

    node = _make_node(1)

    first = await manager.update_node(node)
    assert isinstance(first, _FakePGNode)

    second = await manager.update_node(_make_node(1))

    assert second is first
    assert first.stop_calls == 0
    assert first.set_health_calls == 0

    changed = await manager.update_node(_make_node(1, api_key="rotated-key"))
    assert changed is not first
    assert first.stop_calls == 1
    assert first.set_health_calls == 1


class _AwaitableNone:
    def __await__(self):
        async def _inner():
            return None

        return _inner().__await__()


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
