import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PasarGuardNodeBridge import NodeAPIError

from app.db.models import CoreType, NodeStatus
from app.operation import node as node_op_module
from app.operation.node import CONNECT_CONCURRENCY, NodeOperation


@pytest.mark.asyncio
async def test_connect_node_lifecycle_contender_does_not_overwrite_owner_result(monkeypatch: pytest.MonkeyPatch):
    db_node = SimpleNamespace(id=19, name="node-19", status=NodeStatus.connecting)
    core = SimpleNamespace(type=CoreType.xray)

    monkeypatch.setattr(node_op_module.node_manager, "get_node", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        NodeOperation,
        "_start_or_attach_node",
        AsyncMock(side_effect=NodeAPIError(409, "already in progress")),
    )
    monkeypatch.setattr(NodeOperation, "_attach_if_running", AsyncMock(return_value=None))

    result = await NodeOperation.connect_node(db_node, core, [])

    assert result is None


@pytest.mark.asyncio
async def test_connect_nodes_bulk_local_caps_concurrency(monkeypatch: pytest.MonkeyPatch):
    op = NodeOperation.__new__(NodeOperation)
    current = 0
    peak = 0

    async def _connect_node(db_node, core, users):
        nonlocal current, peak
        current += 1
        peak = max(peak, current)
        await asyncio.sleep(0.01)
        current -= 1
        return {
            "node_id": db_node.id,
            "status": NodeStatus.connected,
            "message": "",
            "xray_version": "",
            "node_version": "",
            "old_status": NodeStatus.connecting,
        }

    monkeypatch.setattr(node_op_module, "node_manager", MagicMock(update_node=AsyncMock()))
    monkeypatch.setattr(NodeOperation, "_get_core_users_map", AsyncMock(return_value=({1: object()}, {1: []})))
    monkeypatch.setattr(NodeOperation, "connect_node", staticmethod(_connect_node))
    monkeypatch.setattr(node_op_module, "bulk_update_node_status", AsyncMock())
    monkeypatch.setattr(node_op_module.notification, "connect_node", AsyncMock())
    monkeypatch.setattr(node_op_module.notification, "error_node", AsyncMock())

    nodes = [
        SimpleNamespace(id=i, status=NodeStatus.connecting, core_config_id=1, name=f"n{i}") for i in range(25)
    ]
    await op._connect_nodes_bulk_local(MagicMock(), nodes)

    assert peak <= CONNECT_CONCURRENCY
    assert peak > 1
