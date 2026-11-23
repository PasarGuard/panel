"""Single-worker lifecycle bridge: attach without shared lifecycle memory, and deadlock-safe node status writes (#1243)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import OperationalError

from PasarGuardNodeBridge.storage import LifecycleStatus

from app.db.crud import node as node_crud_module
from app.db.models import NodeStatus
from app.operation.node import NodeOperation

DEADLOCK_ERROR = OperationalError("statement", {}, OSError(1213, "Deadlock found when trying to get lock"))


@pytest.mark.asyncio
async def test_attach_without_lifecycle_state(monkeypatch: pytest.MonkeyPatch):
    """Single worker has no shared lifecycle memory: still try _attach_if_running."""
    info = SimpleNamespace(node_version="0.5.7", core_version="26.10.31")
    pg_node = SimpleNamespace(get_lifecycle_state=AsyncMock(return_value=None))
    db_node = SimpleNamespace(id=7, name="n7", status=NodeStatus.connecting, keep_alive=60)
    attach = AsyncMock(return_value=info)
    monkeypatch.setattr(NodeOperation, "_attach_if_running", attach)
    users = AsyncMock(return_value=[])

    result = await NodeOperation._start_or_attach_node(pg_node, db_node, object(), users, object())

    attach.assert_awaited_once_with(pg_node, "n7")
    users.assert_not_awaited()
    assert result is info


@pytest.mark.asyncio
async def test_attach_without_lifecycle_state_falls_through_to_start(monkeypatch: pytest.MonkeyPatch):
    """When the node is not already running, a full start is still attempted."""
    info = SimpleNamespace(node_version="0.5.7", core_version="26.10.31")
    pg_node = SimpleNamespace(
        get_lifecycle_state=AsyncMock(return_value=None),
        start=AsyncMock(return_value=info),
    )
    db_node = SimpleNamespace(id=7, name="n7", status=NodeStatus.connecting, keep_alive=60)
    monkeypatch.setattr(NodeOperation, "_attach_if_running", AsyncMock(return_value=None))
    core = SimpleNamespace(type=None, to_str=lambda: "core-config")
    users = AsyncMock(return_value=[])

    result = await NodeOperation._start_or_attach_node(pg_node, db_node, core, users, object())

    NodeOperation._attach_if_running.assert_awaited_once_with(pg_node, "n7")
    users.assert_awaited_once()
    pg_node.start.assert_awaited_once()
    assert result is info


@pytest.mark.asyncio
async def test_shared_lifecycle_healthy_state_still_attaches(monkeypatch: pytest.MonkeyPatch):
    """Multi-worker with shared lifecycle memory keeps the existing attach path."""
    state = SimpleNamespace(observed=LifecycleStatus.HEALTHY, desired=LifecycleStatus.HEALTHY, epoch=1)
    info = SimpleNamespace(node_version="0.5.7", core_version="26.10.31")
    pg_node = SimpleNamespace(get_lifecycle_state=AsyncMock(return_value=state))
    db_node = SimpleNamespace(id=7, name="n7", status=NodeStatus.connecting, keep_alive=60)
    attach = AsyncMock(return_value=info)
    monkeypatch.setattr(NodeOperation, "_attach_if_running", attach)
    users = AsyncMock(return_value=[])

    result = await NodeOperation._start_or_attach_node(pg_node, db_node, object(), users, object())

    attach.assert_awaited_once_with(pg_node, "n7")
    users.assert_not_awaited()
    assert result is info


@pytest.mark.asyncio
async def test_bulk_update_node_status_sorts_by_node_id():
    execute = AsyncMock()
    db = SimpleNamespace(connection=AsyncMock(return_value=SimpleNamespace(execute=execute)), commit=AsyncMock())
    updates = [
        {"node_id": 5, "status": NodeStatus.connected, "message": "", "xray_version": "1", "node_version": "2"},
        {"node_id": 1, "status": NodeStatus.error, "message": "down", "xray_version": "1", "node_version": "2"},
    ]

    await node_crud_module.bulk_update_node_status(db, updates)

    params = execute.await_args.args[1]
    assert [row["node_id"] for row in params] == [1, 5]


@pytest.mark.asyncio
async def test_bulk_update_node_status_retries_on_mysql_deadlock():
    execute = AsyncMock(side_effect=[DEADLOCK_ERROR, None])
    db = SimpleNamespace(
        connection=AsyncMock(return_value=SimpleNamespace(execute=execute)),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    updates = [
        {"node_id": 1, "status": NodeStatus.connected, "message": "", "xray_version": "1", "node_version": "2"},
    ]

    await node_crud_module.bulk_update_node_status(db, updates)

    assert execute.await_count == 2
    db.rollback.assert_awaited_once()
    db.commit.assert_awaited_once()
