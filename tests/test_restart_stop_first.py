from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db.models import NodeStatus
from app.node import worker as worker_module
from app.node.worker import NodeWorkerService
from app.operation import node as node_operation_module
from app.operation.node import NodeOperation


def bare_operation() -> NodeOperation:
    return NodeOperation.__new__(NodeOperation)


@pytest.mark.asyncio
async def test_restart_all_node_passes_stop_first():
    operation = bare_operation()
    operation._restart_all_impl = AsyncMock()
    admin = SimpleNamespace(username="admin")

    await operation.restart_all_node(None, admin, 3, stop_first=False)

    operation._restart_all_impl.assert_awaited_once_with(None, admin, 3, stop_first=False)


@pytest.mark.asyncio
async def test_local_restart_all_passes_stop_first(monkeypatch: pytest.MonkeyPatch):
    nodes = [SimpleNamespace(id=1)]
    monkeypatch.setattr(node_operation_module, "get_nodes", AsyncMock(return_value=(nodes, 1)))
    operation = SimpleNamespace(connect_nodes_bulk=AsyncMock())

    await NodeOperation._restart_all_nodes_local(operation, None, None, 3, stop_first=False)

    operation.connect_nodes_bulk.assert_awaited_once_with(None, nodes, force_start=True, stop_first=False)


@pytest.mark.asyncio
async def test_remote_restart_all_sends_stop_first(monkeypatch: pytest.MonkeyPatch):
    publish = AsyncMock()
    monkeypatch.setattr(node_operation_module.node_nats_client, "publish", publish)

    await NodeOperation._restart_all_nodes_remote(object(), None, None, 3, stop_first=False)

    publish.assert_awaited_once_with("connect_nodes_bulk", {"core_id": 3, "force_start": True, "stop_first": False})


@pytest.mark.asyncio
async def test_connect_nodes_bulk_passes_stop_first():
    operation = bare_operation()
    operation._connect_bulk_impl = AsyncMock()

    await operation.connect_nodes_bulk(None, [], force_start=True, stop_first=False)

    operation._connect_bulk_impl.assert_awaited_once_with(None, [], force_start=True, stop_first=False)


@pytest.mark.asyncio
async def test_sync_bulk_connect_passes_stop_first(monkeypatch: pytest.MonkeyPatch):
    operation = bare_operation()
    operation._connect_nodes_bulk_local = AsyncMock()
    monkeypatch.setattr(node_operation_module, "publish_node_sync", AsyncMock())

    await NodeOperation._connect_nodes_bulk_sync(operation, None, [], force_start=True, stop_first=False)

    operation._connect_nodes_bulk_local.assert_awaited_once_with(None, [], force_start=True, stop_first=False)


@pytest.mark.asyncio
async def test_remote_bulk_connect_sends_stop_first(monkeypatch: pytest.MonkeyPatch):
    publish = AsyncMock()
    monkeypatch.setattr(node_operation_module.node_nats_client, "publish", publish)

    await NodeOperation._connect_nodes_bulk_remote(
        object(), None, [SimpleNamespace(id=4)], force_start=True, stop_first=False
    )

    publish.assert_awaited_once_with("connect_nodes_bulk", {"node_ids": [4], "force_start": True, "stop_first": False})


@pytest.mark.asyncio
async def test_local_bulk_connect_passes_stop_first_to_each_node(monkeypatch: pytest.MonkeyPatch):
    node = SimpleNamespace(id=7, name="n7", status=NodeStatus.connected, core_config_id=2)
    core = object()
    operation = bare_operation()
    operation._get_core_users_map = AsyncMock(return_value=({2: core}, {2: []}))
    monkeypatch.setattr(node_operation_module.node_manager, "update_node", AsyncMock())
    monkeypatch.setattr(node_operation_module, "bulk_update_node_status", AsyncMock())
    connect = AsyncMock(return_value=None)
    monkeypatch.setattr(NodeOperation, "connect_node", connect)

    await NodeOperation._connect_nodes_bulk_local(operation, None, [node], force_start=True, stop_first=False)

    connect.assert_awaited_once_with(node, core, [], force_start=True, stop_first=False)


@pytest.mark.asyncio
async def test_connect_node_passes_stop_first(monkeypatch: pytest.MonkeyPatch):
    db_node = SimpleNamespace(id=19, name="n19", status=NodeStatus.connected, keep_alive=60)
    monkeypatch.setattr(node_operation_module.node_manager, "get_node", AsyncMock(return_value=object()))
    start = AsyncMock(return_value=SimpleNamespace(node_version="0.5.5", core_version="26.10.10"))
    monkeypatch.setattr(NodeOperation, "_start_or_attach_node", start)

    result = await NodeOperation.connect_node(
        db_node, SimpleNamespace(type=None), [], force_start=True, stop_first=False
    )

    assert result["status"] == NodeStatus.connected
    assert start.await_args.kwargs == {"force_start": True, "stop_first": False}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"core_id": 2, "force_start": True, "stop_first": False}, False),
        # Sent by an API process that predates stop_first.
        ({"core_id": 2, "force_start": True}, True),
    ],
)
async def test_worker_bulk_connect_reads_stop_first(monkeypatch: pytest.MonkeyPatch, payload, expected):
    @asynccontextmanager
    async def fake_db():
        yield "db"

    nodes = [SimpleNamespace(id=1)]
    monkeypatch.setattr(worker_module.core_manager, "_reload_from_cache", AsyncMock())
    monkeypatch.setattr(worker_module, "GetDB", fake_db)
    monkeypatch.setattr(worker_module, "get_nodes", AsyncMock(return_value=(nodes, 1)))
    service = SimpleNamespace(_node_operator=SimpleNamespace(connect_nodes_bulk=AsyncMock()))

    await NodeWorkerService._connect_nodes_bulk(service, payload)

    service._node_operator.connect_nodes_bulk.assert_awaited_once_with(
        "db", nodes, force_start=True, stop_first=expected
    )
