from unittest.mock import AsyncMock

import pytest

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

    async def _remove(
        node_id: int,
        *,
        remote_stop: bool = True,
        permanent_delete: bool = False,
        expected_bridge_namespace: str | None = None,
    ):
        assert permanent_delete is True
        assert expected_bridge_namespace == "bridge-7"
        removed.append((node_id, remote_stop))

    monkeypatch.setattr("app.node.manager_sync.node_manager.remove_node", _remove)

    await handle_node_message(
        {"action": "remove", "node_id": 7, "bridge_id": "bridge-7", "origin": "other-worker"}
    )
    assert removed == [(7, False)]


@pytest.mark.asyncio
async def test_handle_node_remove_failure_retains_shared_memory(monkeypatch: pytest.MonkeyPatch):
    async def _remove(
        _node_id: int,
        *,
        remote_stop: bool = True,
        permanent_delete: bool = False,
        expected_bridge_namespace: str | None = None,
    ):
        assert permanent_delete is True
        assert expected_bridge_namespace == "bridge-7"
        raise RuntimeError("local runtime is not quiescent")

    monkeypatch.setattr("app.node.manager_sync.node_manager.remove_node", _remove)

    with pytest.raises(RuntimeError, match="not quiescent"):
        await handle_node_message(
            {"action": "remove", "node_id": 7, "bridge_id": "bridge-7", "origin": "other-worker"}
        )


@pytest.mark.asyncio
async def test_remove_message_propagates_stable_bridge_namespace(monkeypatch: pytest.MonkeyPatch):
    remove = []

    async def _remove(
        node_id: int,
        *,
        remote_stop: bool = True,
        expected_bridge_namespace: str | None = None,
        permanent_delete: bool = False,
    ):
        assert permanent_delete is True
        remove.append((node_id, remote_stop, expected_bridge_namespace))

    monkeypatch.setattr("app.node.manager_sync.node_manager.remove_node", _remove)

    await handle_node_message(
        {"action": "remove", "node_id": 7, "bridge_id": "old-bridge-id", "origin": "other-worker"}
    )

    assert remove == [(7, False, "old-bridge-id")]



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
async def test_legacy_remove_without_namespace_cannot_delete_reused_numeric_id(monkeypatch):
    remove = AsyncMock()
    monkeypatch.setattr("app.node.manager_sync.node_manager.remove_node", remove)

    await handle_node_message({"action": "remove", "node_id": 7, "origin": "old-worker"})

    remove.assert_not_awaited()


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

    async def _remove(node_id: int, *, remote_stop: bool = True):
        removed.append((node_id, remote_stop))

    monkeypatch.setattr("app.node.manager_sync.node_manager.remove_node", _remove)

    await handle_node_message({"action": "disconnect", "node_id": 3, "origin": "other"})
    assert removed == [(3, False)]


@pytest.mark.asyncio
async def test_handle_node_upsert(monkeypatch: pytest.MonkeyPatch):
    class _Node:
        id = 9

    updated: list[object] = []

    class _DB:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return False

    async def _get_node_by_id(db, node_id, load_usage_logs=False):
        assert node_id == 9
        return _Node()

    async def _update_node(db_node):
        updated.append(db_node)

    monkeypatch.setattr("app.node.manager_sync.GetDB", lambda: _DB())
    monkeypatch.setattr("app.node.manager_sync.get_node_by_id", _get_node_by_id)
    monkeypatch.setattr("app.node.manager_sync.node_manager.update_node", _update_node)
    monkeypatch.setattr("app.node.manager_sync.node_manager.runtime_matches", AsyncMock(return_value=False))

    await handle_node_message({"action": "upsert", "node_id": 9, "origin": "other"})
    assert len(updated) == 1
    assert updated[0].id == 9


@pytest.mark.asyncio
async def test_cross_worker_connect_holds_snapshot_transaction_through_apply(monkeypatch: pytest.MonkeyPatch):
    from app.operation.node import NodeOperation

    events: list[str] = []
    transaction_active = False

    class _Node:
        id = 11
        bridge_id = "bridge-11"
        status = "connecting"
        core_config_id = 1

    class _DB:
        async def __aenter__(self):
            nonlocal transaction_active
            transaction_active = True
            events.append("db-enter")
            return self

        async def __aexit__(self, *_args):
            nonlocal transaction_active
            events.append("db-exit")
            transaction_active = False
            return False

    async def _get_node(*_args, **_kwargs):
        events.append("load-node")
        return _Node()

    async def _register(_node):
        assert transaction_active
        events.append("register-runtime")

    async def _snapshot(_db, _core_ids):
        assert transaction_active
        assert events[-1] == "register-runtime"
        events.append("lock-snapshot")
        return {1: object()}, {1: []}, {"user-sync-id"}

    async def _apply(*_args):
        assert transaction_active
        assert events[-1] == "lock-snapshot"
        events.append("authoritative-apply")

    monkeypatch.setattr("app.node.manager_sync.GetDB", lambda: _DB())
    monkeypatch.setattr("app.node.manager_sync.get_node_by_id", _get_node)
    monkeypatch.setattr("app.node.manager_sync.node_manager.update_node", _register)
    monkeypatch.setattr("app.node.manager_sync.node_manager.runtime_matches", AsyncMock(return_value=False))
    monkeypatch.setattr(NodeOperation, "_get_core_users_map", _snapshot)
    monkeypatch.setattr(NodeOperation, "connect_node", _apply)

    await handle_node_message(
        {"action": "connect", "node_id": 11, "bridge_id": "bridge-11", "origin": "other"}
    )

    assert events == [
        "db-enter",
        "load-node",
        "register-runtime",
        "lock-snapshot",
        "authoritative-apply",
        "db-exit",
    ]


@pytest.mark.asyncio
async def test_duplicate_connect_keeps_matching_runtime_but_reconciles_users(monkeypatch):
    from app.operation.node import NodeOperation

    class _Node:
        id = 12
        bridge_id = "bridge-12"
        status = "connected"
        core_config_id = 1

    class _DB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    update = AsyncMock()
    apply = AsyncMock()
    monkeypatch.setattr("app.node.manager_sync.GetDB", lambda: _DB())
    monkeypatch.setattr(
        "app.node.manager_sync.get_node_by_id",
        AsyncMock(return_value=_Node()),
    )
    monkeypatch.setattr(
        "app.node.manager_sync.node_manager.runtime_matches",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr("app.node.manager_sync.node_manager.update_node", update)
    monkeypatch.setattr(
        NodeOperation,
        "_get_core_users_map",
        AsyncMock(return_value=({1: object()}, {1: []}, {"sync-user"})),
    )
    monkeypatch.setattr(NodeOperation, "connect_node", apply)

    await handle_node_message(
        {"action": "connect", "node_id": 12, "bridge_id": "bridge-12", "origin": "other"}
    )

    update.assert_not_awaited()
    apply.assert_awaited_once()
