from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from PasarGuardNodeBridge import Health, NodeAPIError

from app.db.models import NodeStatus
from app.node import worker as worker_module
from app.node.worker import NodeWorkerService
from app.operation import OperatorType, node as node_operation
from app.operation.node import NodeOperation
from config import runtime_settings
from role import Role


@pytest.mark.parametrize("status", [NodeStatus.connected, NodeStatus.disabled, NodeStatus.limited])
async def test_hard_reset_schedules_reconnect_without_enabling_node(monkeypatch, status):
    db_node = SimpleNamespace(id=7, status=status)
    node = SimpleNamespace(
        hard_reset=AsyncMock(return_value=SimpleNamespace(json=lambda: {"detail": "restarted"})),
        set_health=AsyncMock(),
    )
    monkeypatch.setattr(node_operation.node_manager, "get_node", AsyncMock(return_value=node))
    monkeypatch.setattr(node_operation, "get_node_by_id", AsyncMock(return_value=db_node))
    update_status = AsyncMock()
    monkeypatch.setattr(node_operation, "update_node_status", update_status)
    db = object()
    assert await NodeOperation(OperatorType.API)._hard_reset_node_local(db, 7) == {"detail": "restarted"}
    node.hard_reset.assert_awaited_once_with()
    if status == NodeStatus.connected:
        update_status.assert_awaited_once_with(
            db, db_node, NodeStatus.connecting, message="", xray_version="", node_version=""
        )
        node.set_health.assert_awaited_once_with(Health.NOT_CONNECTED)
    else:
        update_status.assert_not_awaited()


@pytest.mark.parametrize("code", [409, 500, 503])
async def test_failed_hard_reset_preserves_status(monkeypatch, code):
    node = SimpleNamespace(hard_reset=AsyncMock(side_effect=NodeAPIError(code, "reset failed")))
    monkeypatch.setattr(node_operation.node_manager, "get_node", AsyncMock(return_value=node))
    mark_reconnecting = AsyncMock()
    monkeypatch.setattr(NodeOperation, "_mark_node_reconnecting_after_update", mark_reconnecting)
    with pytest.raises(HTTPException) as exc:
        await NodeOperation(OperatorType.API)._hard_reset_node_local(None, 7)
    assert exc.value.status_code == code
    assert exc.value.detail == "reset failed"
    mark_reconnecting.assert_not_awaited()


async def test_hard_reset_missing_bridge(monkeypatch):
    monkeypatch.setattr(node_operation.node_manager, "get_node", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        await NodeOperation(OperatorType.API)._hard_reset_node_local(None, 7)
    assert exc.value.status_code == 404


@pytest.mark.parametrize("role", [Role.ALL_IN_ONE, Role.BACKEND])
async def test_hard_reset_dispatches_for_process_role(monkeypatch, role):
    monkeypatch.setattr(runtime_settings, "role", role)
    local = AsyncMock(return_value={"local": True})
    remote = AsyncMock(return_value={"remote": True})
    monkeypatch.setattr(NodeOperation, "_hard_reset_node_local", local)
    monkeypatch.setattr(NodeOperation, "_hard_reset_node_remote", remote)
    validate = AsyncMock()
    monkeypatch.setattr(NodeOperation, "get_validated_node", validate)
    db = object()
    result = await NodeOperation(OperatorType.API).hard_reset_node(db, 7)
    validate.assert_awaited_once_with(db, 7, load_usage_logs=False)
    selected, unused = (local, remote) if role.runs_node else (remote, local)
    selected.assert_awaited_once_with(db, 7)
    unused.assert_not_awaited()
    assert result == selected.return_value


async def test_hard_reset_worker_handler(monkeypatch):
    db = object()

    @asynccontextmanager
    async def get_db():
        yield db

    monkeypatch.setattr(worker_module, "GetDB", get_db)
    worker = NodeWorkerService()
    worker._node_operator = SimpleNamespace(hard_reset_node=AsyncMock(return_value={"detail": "restarted"}))
    assert await worker._hard_reset_node({"node_id": 7}) == {"detail": "restarted"}
    worker._node_operator.hard_reset_node.assert_awaited_once_with(db, 7)
    with pytest.raises(RuntimeError, match="node_id is required"):
        await worker._hard_reset_node({})
