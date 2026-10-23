from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PasarGuardNodeBridge import Health

from app.db.models import NodeStatus
from app.jobs import node_checker
from app.models.node import NodeCoreUpdate
from app.operation import OperatorType, node as node_operation
from app.operation.node import NodeOperation


@pytest.mark.asyncio
async def test_core_update_leaves_reconnection_to_health_job(monkeypatch):
    db_node = SimpleNamespace(id=7, status=NodeStatus.connected, node_version="0.5.4", xray_version="25.1.1")
    db = object()
    response = SimpleNamespace(json=lambda: {"detail": "node core updated successfully"})
    node = SimpleNamespace(
        update_core=AsyncMock(return_value=response),
        set_health=AsyncMock(),
    )
    monkeypatch.setattr(node_operation.node_manager, "get_node", AsyncMock(return_value=node))
    monkeypatch.setattr(node_operation, "get_node_by_id", AsyncMock(return_value=db_node))
    update_status = AsyncMock()
    monkeypatch.setattr(node_operation, "update_node_status", update_status)

    operation = NodeOperation(OperatorType.SYSTEM)
    result = await operation._update_core_local(db, 7, NodeCoreUpdate(core_version="v26.10.21"))

    assert result == {"detail": "node core updated successfully"}
    update_status.assert_awaited_once_with(
        db, db_node, NodeStatus.connecting, message="", xray_version="", node_version=""
    )
    node.set_health.assert_awaited_once_with(Health.NOT_CONNECTED)


@pytest.mark.asyncio
async def test_node_update_leaves_reconnection_to_health_job(monkeypatch):
    db_node = SimpleNamespace(id=7, status=NodeStatus.connected, node_version="0.5.4", xray_version="26.10.21")
    db = object()
    node = SimpleNamespace(
        update_node=AsyncMock(return_value=SimpleNamespace(json=lambda: {"detail": "node updated successfully"})),
        set_health=AsyncMock(),
    )
    monkeypatch.setattr(node_operation.node_manager, "get_node", AsyncMock(return_value=node))
    monkeypatch.setattr(node_operation, "get_node_by_id", AsyncMock(return_value=db_node))
    update_status = AsyncMock()
    monkeypatch.setattr(node_operation, "update_node_status", update_status)

    operation = NodeOperation(OperatorType.SYSTEM)
    assert await operation._update_node_api_local(db, 7) == {"detail": "node updated successfully"}
    update_status.assert_awaited_once_with(
        db, db_node, NodeStatus.connecting, message="", xray_version="", node_version=""
    )
    node.set_health.assert_awaited_once_with(Health.NOT_CONNECTED)


@pytest.mark.asyncio
async def test_version_refresh_does_not_write_for_a_replaced_connection(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock())
    node = SimpleNamespace(
        info=AsyncMock(return_value=SimpleNamespace(started=True, node_version="0.5.5", core_version="26.10.21")),
        set_reported_versions=AsyncMock(),
    )
    monkeypatch.setattr(node_operation.node_manager, "get_node", AsyncMock(return_value=object()))
    get_db_node = AsyncMock()
    monkeypatch.setattr(node_operation, "get_node_by_id", get_db_node)

    assert not await NodeOperation.refresh_node_versions(db, 7, node)
    get_db_node.assert_not_awaited()
    db.commit.assert_not_awaited()
    node.set_reported_versions.assert_not_awaited()


@pytest.mark.asyncio
async def test_follower_refreshes_bridge_cache_without_writing_database(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock())
    node = SimpleNamespace(
        info=AsyncMock(return_value=SimpleNamespace(started=True, node_version="0.5.5", core_version="26.10.21")),
        set_reported_versions=AsyncMock(),
    )
    monkeypatch.setattr(node_operation.node_manager, "get_node", AsyncMock(return_value=node))
    get_db_node = AsyncMock()
    monkeypatch.setattr(node_operation, "get_node_by_id", get_db_node)

    assert await NodeOperation.refresh_node_versions(db, 7, node, persist=False)
    get_db_node.assert_not_awaited()
    db.commit.assert_not_awaited()
    node.set_reported_versions.assert_awaited_once_with("0.5.5", "26.10.21")


@pytest.mark.asyncio
async def test_healthy_connected_node_eventually_refreshes_versions(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(node_checker, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(node_checker, "_health_streaks", {})
    monkeypatch.setattr(node_checker, "_version_refresh_deadlines", {})
    monkeypatch.setattr(node_checker, "_owns_health_checks", lambda: True)
    monkeypatch.setattr(node_checker, "needs_shared_bridge_memory", lambda: False)
    monkeypatch.setattr(node_checker, "verify_node_backend_health", AsyncMock(return_value=(Health.HEALTHY, None, None)))
    refresh = AsyncMock(return_value=True)
    monkeypatch.setattr(NodeOperation, "refresh_node_versions", refresh)

    class FakeDB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(node_checker, "GetDB", FakeDB)
    node = SimpleNamespace(
        requires_hard_reset=lambda: False,
        get_health=AsyncMock(return_value=Health.HEALTHY),
        set_health=AsyncMock(),
    )
    db_node = SimpleNamespace(id=7, name="node", status=NodeStatus.connected, default_timeout=10)

    await node_checker.process_node_health_check(db_node, node)
    refresh.assert_not_awaited()
    clock[0] += node_checker._VERSION_REFRESH_INTERVAL
    await node_checker.process_node_health_check(db_node, node)
    refresh.assert_awaited_once()
