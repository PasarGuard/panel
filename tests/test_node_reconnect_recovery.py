import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PasarGuardNodeBridge import Health
from PasarGuardNodeBridge.storage import LifecycleStatus

from app.db.models import NodeStatus
from app.jobs import node_checker
from app.node import manager_sync
from app.operation import node as node_operation
from app.operation.node import NodeOperation


class FakeDB:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def setup_node(monkeypatch, *, health=Health.HEALTHY, state=None):
    db_node = SimpleNamespace(id=91, name="node", status=NodeStatus.connected, core_config_id=1, keep_alive=60)
    core = SimpleNamespace(type=None, inbounds=["in"], protocols=frozenset(), to_str=lambda: "{}")
    info = SimpleNamespace(started=True, node_version="0.5.4", core_version="26.3.27")
    node = SimpleNamespace(
        get_health=AsyncMock(return_value=health),
        get_versions=AsyncMock(return_value=(info.node_version, info.core_version)),
        get_lifecycle_state=AsyncMock(return_value=state),
        info=AsyncMock(return_value=info),
        connect=AsyncMock(),
        _work_available=asyncio.Event(),
        _ensure_sync_worker_running=AsyncMock(),
        update_observed_lifecycle=AsyncMock(),
        start=AsyncMock(return_value=info),
        stop=AsyncMock(),
    )
    monkeypatch.setattr(manager_sync, "GetDB", FakeDB)
    monkeypatch.setattr(manager_sync, "get_node_by_id", AsyncMock(return_value=db_node))
    monkeypatch.setattr(node_operation, "get_node_by_id", AsyncMock(return_value=db_node))
    monkeypatch.setattr(node_operation.core_manager, "get_cores", AsyncMock(return_value={1: core}))
    monkeypatch.setattr(node_operation.node_manager, "update_node", AsyncMock(return_value=node))
    monkeypatch.setattr(node_operation.node_manager, "get_node", AsyncMock(return_value=node))
    reads = AsyncMock(return_value=[object()])
    monkeypatch.setattr(node_operation, "core_users", reads)
    monkeypatch.setattr(node_operation, "update_node_status", AsyncMock())
    monkeypatch.setattr(node_operation, "bulk_update_node_status", AsyncMock())
    monkeypatch.setattr(node_operation.notification, "connect_node", AsyncMock())
    monkeypatch.setattr(node_operation.notification, "error_node", AsyncMock())
    return db_node, node, reads


@pytest.mark.asyncio
async def test_repeated_connect_broadcasts_do_not_load_users_for_healthy_node(monkeypatch):
    db_node, node, reads = setup_node(monkeypatch)
    for _ in range(40):
        await manager_sync.handle_node_message({"action": "connect", "node_id": db_node.id, "origin": "other"})
    reads.assert_not_awaited()
    node.start.assert_not_awaited()
    node.stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_sibling_attaches_to_running_core_without_loading_users(monkeypatch):
    state = SimpleNamespace(desired=LifecycleStatus.HEALTHY, observed=LifecycleStatus.HEALTHY, epoch=3)
    db_node, node, reads = setup_node(monkeypatch, health=Health.NOT_CONNECTED, state=state)
    await manager_sync.handle_node_message({"action": "connect", "node_id": db_node.id, "origin": "other"})
    node.connect.assert_awaited_once()
    reads.assert_not_awaited()
    node.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_shared_attachment_wakes_persisted_work_without_enqueuing_users(monkeypatch):
    state = SimpleNamespace(desired=LifecycleStatus.HEALTHY, observed=LifecycleStatus.HEALTHY, epoch=3)
    db_node, node, reads = setup_node(monkeypatch, health=Health.NOT_CONNECTED, state=state)
    monkeypatch.setattr(node_operation, "needs_shared_bridge_memory", lambda: True)
    await manager_sync.handle_node_message({"action": "connect", "node_id": db_node.id, "origin": "other"})
    assert node._work_available.is_set()
    node._ensure_sync_worker_running.assert_awaited_once()
    reads.assert_not_awaited()
    node.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_sibling_loads_users_when_remote_core_needs_start(monkeypatch):
    db_node, node, reads = setup_node(monkeypatch, health=Health.NOT_CONNECTED)
    await manager_sync.handle_node_message({"action": "connect", "node_id": db_node.id, "origin": "other"})
    reads.assert_awaited_once()
    assert node.start.await_args.kwargs["users"] is reads.return_value


@pytest.mark.asyncio
async def test_bulk_start_reuses_one_deferred_snapshot_per_core(monkeypatch):
    db_node, node, reads = setup_node(monkeypatch, health=Health.NOT_CONNECTED)
    nodes = [SimpleNamespace(**(vars(db_node) | {"id": index})) for index in range(12)]
    operation = NodeOperation.__new__(NodeOperation)
    await operation._connect_nodes_bulk_local(FakeDB(), nodes)
    reads.assert_awaited_once()
    assert node.start.await_count == 12
    assert all(call.kwargs["users"] is reads.return_value for call in node.start.await_args_list)


@pytest.mark.asyncio
async def test_deferred_core_reads_do_not_overlap_on_shared_session(monkeypatch):
    cores = {index: SimpleNamespace(inbounds=[str(index)], protocols=frozenset()) for index in (1, 2)}
    monkeypatch.setattr(node_operation.core_manager, "get_cores", AsyncMock(return_value=cores))
    active = 0

    async def read(*, db, inbound_tags, allowed_protocols):
        nonlocal active
        assert active == 0
        active += 1
        await asyncio.sleep(0.01)
        active -= 1
        return inbound_tags

    reads = AsyncMock(side_effect=read)
    monkeypatch.setattr(node_operation, "core_users", reads)
    _, loaders = await NodeOperation._get_core_users_map(FakeDB(), {1, 2}, lazy=True)
    reads.assert_not_awaited()
    result = await asyncio.gather(loaders[1](), loaders[2](), loaders[1](), loaders[2]())
    assert result == [["1"], ["2"], ["1"], ["2"]]
    assert reads.await_count == 2


@pytest.mark.asyncio
async def test_forced_start_still_loads_users_and_restarts_healthy_core(monkeypatch):
    db_node, node, reads = setup_node(monkeypatch)
    operation = NodeOperation.__new__(NodeOperation)
    publish = AsyncMock()
    monkeypatch.setattr(node_operation, "publish_node_sync", publish)
    await operation._connect_single_node_sync(FakeDB(), db_node.id, force_start=True)
    reads.assert_awaited_once()
    node.stop.assert_awaited_once()
    node.start.assert_awaited_once()
    publish.assert_awaited_once_with("connect", db_node.id)


@pytest.mark.asyncio
async def test_failed_snapshot_does_not_stop_healthy_core(monkeypatch):
    db_node, node, reads = setup_node(monkeypatch)
    reads.side_effect = RuntimeError("database unavailable")
    operation = NodeOperation.__new__(NodeOperation)
    with pytest.raises(RuntimeError, match="database unavailable"):
        await operation._connect_single_node_local(FakeDB(), db_node.id, force_start=True)
    node.stop.assert_not_awaited()
    node.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_unchanged_connection_does_not_broadcast_or_reload_users(monkeypatch):
    db_node, node, reads = setup_node(monkeypatch)
    operation = NodeOperation.__new__(NodeOperation)
    publish = AsyncMock()
    monkeypatch.setattr(node_operation, "publish_node_sync", publish)
    for _ in range(10):
        await operation._connect_single_node_sync(FakeDB(), db_node.id)
    reads.assert_not_awaited()
    publish.assert_not_awaited()
    node.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_sync_recovers_local_attachment_with_cooldown(monkeypatch):
    db_node, node, reads = setup_node(monkeypatch)
    node.requires_hard_reset = MagicMock(return_value=True)
    clock = [100.0]
    monkeypatch.setattr(node_checker, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(node_checker, "_sync_recovery_deadlines", {})
    monkeypatch.setattr(
        node_checker, "verify_node_backend_health", AsyncMock(return_value=(Health.HEALTHY, None, None))
    )
    attach = AsyncMock(return_value=None)
    monkeypatch.setattr(NodeOperation, "_attach_if_running", attach)
    reconnect = AsyncMock()
    monkeypatch.setattr(node_checker.node_operator, "connect_single_node", reconnect)
    for _ in range(20):
        await node_checker.process_node_health_check(db_node, node)
    attach.assert_awaited_once()
    clock[0] += 60
    await node_checker.process_node_health_check(db_node, node)
    assert attach.await_count == 2
    reconnect.assert_not_awaited()
    reads.assert_not_awaited()
    node.stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_sync_does_not_mask_dead_backend(monkeypatch):
    db_node, node, _ = setup_node(monkeypatch, health=Health.BROKEN)
    node.requires_hard_reset = MagicMock(return_value=True)
    monkeypatch.setattr(node_checker, "GetDB", FakeDB)
    monkeypatch.setattr(node_checker, "get_bridge_memory", lambda: (None, None, None))
    monkeypatch.setattr(NodeOperation, "_update_single_node_status", AsyncMock())
    monkeypatch.setattr(
        node_checker,
        "verify_node_backend_health",
        AsyncMock(return_value=(Health.BROKEN, 500, "backend not initialized")),
    )
    reconnect = AsyncMock()
    monkeypatch.setattr(node_checker.node_operator, "connect_single_node", reconnect)
    await node_checker.process_node_health_check(db_node, node)
    reconnect.assert_awaited_once()
