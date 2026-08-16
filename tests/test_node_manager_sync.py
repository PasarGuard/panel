import pytest

from app.db.models import NodeStatus
from app.nats.router import _router_enabled
from app.node.manager_sync import handle_node_message
from role import Role


def test_router_enabled_for_all_in_one_multi_worker(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.nats.router.runtime_settings.role", Role.ALL_IN_ONE)
    monkeypatch.setattr("app.nats.router.server_settings.workers", 2)
    monkeypatch.setattr("app.nats.router.nats_settings.enabled", True)
    assert _router_enabled() is True


def test_router_disabled_without_nats(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.nats.router.runtime_settings.role", Role.ALL_IN_ONE)
    monkeypatch.setattr("app.nats.router.server_settings.workers", 2)
    monkeypatch.setattr("app.nats.router.nats_settings.enabled", False)
    assert _router_enabled() is False


@pytest.mark.asyncio
async def test_handle_node_remove(monkeypatch: pytest.MonkeyPatch):
    removed: list[tuple[int, bool]] = []
    cleared: list[int] = []

    async def _remove(node_id: int, *, remote_stop: bool = True):
        removed.append((node_id, remote_stop))

    async def _clear(node_id):
        cleared.append(int(node_id))

    monkeypatch.setattr("app.node.manager_sync.node_manager.remove_node", _remove)
    monkeypatch.setattr("app.node.manager_sync.clear_bridge_memory_for_node", _clear)

    await handle_node_message({"action": "remove", "node_id": 7, "origin": "other-worker"})
    assert removed == [(7, False)]
    assert cleared == [7]


@pytest.mark.asyncio
async def test_handle_node_ignores_own_origin(monkeypatch: pytest.MonkeyPatch):
    removed: list[tuple[int, bool]] = []

    async def _remove(node_id: int, *, remote_stop: bool = True):
        removed.append((node_id, remote_stop))

    monkeypatch.setattr("app.node.manager_sync.node_manager.remove_node", _remove)
    monkeypatch.setattr("app.node.manager_sync.WORKER_ID", "worker-self")

    await handle_node_message({"action": "remove", "node_id": 7, "origin": "worker-self"})
    assert removed == []


@pytest.mark.asyncio
async def test_publish_node_sync_includes_origin(monkeypatch: pytest.MonkeyPatch):
    from app.node.manager_sync import publish_node_sync

    published: list[dict] = []

    async def _publish(topic, data):
        published.append(data)

    monkeypatch.setattr("app.node.manager_sync.router.publish", _publish)
    monkeypatch.setattr("app.node.manager_sync.WORKER_ID", "worker-a")

    await publish_node_sync("upsert", 42)
    assert published == [{"action": "upsert", "node_id": 42, "origin": "worker-a"}]


@pytest.mark.asyncio
async def test_handle_node_disconnect_no_memory_clear(monkeypatch: pytest.MonkeyPatch):
    removed: list[tuple[int, bool]] = []
    cleared: list[int] = []

    async def _remove(node_id: int, *, remote_stop: bool = True):
        removed.append((node_id, remote_stop))

    async def _clear(node_id):
        cleared.append(int(node_id))

    monkeypatch.setattr("app.node.manager_sync.node_manager.remove_node", _remove)
    monkeypatch.setattr("app.node.manager_sync.clear_bridge_memory_for_node", _clear)

    await handle_node_message({"action": "disconnect", "node_id": 3, "origin": "other"})
    assert removed == [(3, False)]
    assert cleared == []


@pytest.mark.asyncio
async def test_handle_node_upsert(monkeypatch: pytest.MonkeyPatch):
    class _Node:
        id = 9

    updated: list[tuple[object, bool]] = []

    class _DB:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return False

    async def _get_node_by_id(db, node_id, load_usage_logs=False):
        assert node_id == 9
        return _Node()

    async def _update_node(db_node, *, remote_stop=True):
        updated.append((db_node, remote_stop))

    monkeypatch.setattr("app.node.manager_sync.GetDB", lambda: _DB())
    monkeypatch.setattr("app.node.manager_sync.get_node_by_id", _get_node_by_id)
    monkeypatch.setattr("app.node.manager_sync.node_manager.update_node", _update_node)

    await handle_node_message({"action": "upsert", "node_id": 9, "origin": "other"})
    assert len(updated) == 1
    assert updated[0][0].id == 9
    assert updated[0][1] is False


@pytest.mark.asyncio
async def test_handle_node_connect_replaces_local_controller_without_remote_stop(monkeypatch: pytest.MonkeyPatch):
    class _Node:
        id = 9
        name = "node-9"
        core_config_id = 1
        status = NodeStatus.error

    updates: list[bool] = []
    connects: list[int] = []

    class _DB:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return False

    async def _get_node_by_id(db, node_id, load_usage_logs=False):
        return _Node()

    async def _update_node(db_node, *, remote_stop=True):
        updates.append(remote_stop)

    async def _get_core_users_map(db, core_ids):
        return {1: object()}, {1: []}

    async def _connect_node(db_node, core, users):
        connects.append(db_node.id)

    monkeypatch.setattr("app.node.manager_sync.GetDB", lambda: _DB())
    monkeypatch.setattr("app.node.manager_sync.get_node_by_id", _get_node_by_id)
    monkeypatch.setattr("app.node.manager_sync.node_manager.update_node", _update_node)
    monkeypatch.setattr("app.operation.node.NodeOperation._get_core_users_map", _get_core_users_map)
    monkeypatch.setattr("app.operation.node.NodeOperation.connect_node", _connect_node)

    await handle_node_message({"action": "connect", "node_id": 9, "origin": "other"})

    assert updates == [False]
    assert connects == [9]
