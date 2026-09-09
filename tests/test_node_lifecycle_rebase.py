import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PasarGuardNodeBridge import Health, NodeAPIError
from PasarGuardNodeBridge.storage import LifecycleOperation, LifecycleStatus

import app.node as node_module
import app.operation.node as node_operation_module
from app.db.models import NodeStatus
from app.node import NodeManager
from app.operation.node import NodeOperation


@pytest.mark.asyncio
async def test_connect_holds_runtime_against_concurrent_remove(monkeypatch: pytest.MonkeyPatch):
    """A completed Start must not publish CONNECTED for a runtime already removed."""
    manager = NodeManager()
    manager._uses_shared_revocation_store = False
    runtime = SimpleNamespace(
        node_id="bridge-1",
        _lifecycle_coordinator=None,
        get_health=AsyncMock(return_value=Health.BROKEN),
        set_health=AsyncMock(),
        disconnect=AsyncMock(),
    )
    manager._nodes[1] = runtime
    entered_start = asyncio.Event()
    release_start = asyncio.Event()

    async def slow_start(*_args, **_kwargs):
        entered_start.set()
        await release_start.wait()
        return SimpleNamespace(node_version="node-v", core_version="core-v")

    monkeypatch.setattr(node_operation_module, "node_manager", manager)
    monkeypatch.setattr(node_module, "ensure_bridge_memory", AsyncMock())
    monkeypatch.setattr(node_module, "get_bridge_memory", lambda: (None, None, "worker"))
    monkeypatch.setattr(NodeOperation, "_start_or_attach_node", slow_start)

    db_node = SimpleNamespace(id=1, name="node", status=NodeStatus.error)
    core = SimpleNamespace(type=object())
    connect = asyncio.create_task(NodeOperation.connect_node(db_node, core, [], set()))
    await entered_start.wait()
    remove = asyncio.create_task(manager.remove_node(1, remote_stop=False))
    try:
        completed, _ = await asyncio.wait({remove}, timeout=0.05)
        assert not completed, "remove raced past an in-flight Start using the same runtime"
    finally:
        release_start.set()
        await asyncio.gather(connect, remove, return_exceptions=True)


@pytest.mark.asyncio
async def test_permanent_delete_marks_namespace_before_waiting_for_runtime_transition(
    monkeypatch: pytest.MonkeyPatch,
):
    """Deletion intent must fence a slow Start/replacement before waiting for it."""
    manager = NodeManager()
    manager._uses_shared_revocation_store = True
    coordinator = SimpleNamespace(mark_deleted=AsyncMock(), is_deleted=AsyncMock(return_value=False))
    monkeypatch.setattr(node_module, "ensure_bridge_memory", AsyncMock())
    monkeypatch.setattr(node_module, "get_bridge_memory", lambda: (object(), coordinator, "worker"))

    transition_lock = manager._runtime_transition_locks.setdefault(1, asyncio.Lock())
    await transition_lock.acquire()
    remove = asyncio.create_task(
        manager.remove_node(
            1,
            remote_stop=False,
            expected_bridge_namespace="bridge-1",
            permanent_delete=True,
        )
    )
    try:
        await asyncio.sleep(0)
        coordinator.mark_deleted.assert_awaited_once_with("bridge-1")
    finally:
        transition_lock.release()
        await asyncio.gather(remove, return_exceptions=True)
    coordinator.mark_deleted.assert_awaited_once_with("bridge-1")


@pytest.mark.asyncio
async def test_slow_durable_delete_does_not_block_other_topology_reads(monkeypatch: pytest.MonkeyPatch):
    manager = NodeManager()
    manager._uses_shared_revocation_store = True
    other_node = object()
    manager._nodes[2] = other_node
    writing_fence = asyncio.Event()
    release_fence = asyncio.Event()

    async def slow_fence(_namespace):
        writing_fence.set()
        await release_fence.wait()

    coordinator = SimpleNamespace(mark_deleted=AsyncMock(side_effect=slow_fence))
    monkeypatch.setattr(node_module, "ensure_bridge_memory", AsyncMock())
    monkeypatch.setattr(node_module, "get_bridge_memory", lambda: (object(), coordinator, "worker"))
    remove = asyncio.create_task(
        manager.remove_node(1, remote_stop=False, expected_bridge_namespace="bridge-1", permanent_delete=True)
    )
    try:
        await asyncio.wait_for(writing_fence.wait(), timeout=1)
        assert manager.is_bridge_namespace_deleted("bridge-1")
        assert await asyncio.wait_for(manager.get_node(2), timeout=1) is other_node
    finally:
        release_fence.set()
        await remove
    coordinator.mark_deleted.assert_awaited_once_with("bridge-1")


@pytest.mark.asyncio
async def test_force_start_does_not_override_unknown_lifecycle_operation():
    state = SimpleNamespace(
        operation=LifecycleOperation.START,
        observed=LifecycleStatus.STARTING,
        desired=LifecycleStatus.HEALTHY,
    )
    runtime = SimpleNamespace(
        node_id="bridge-2",
        _lifecycle_coordinator=None,
        get_lifecycle_state=AsyncMock(return_value=state),
        info=AsyncMock(),
        stop=AsyncMock(),
        start=AsyncMock(),
    )

    with pytest.raises(NodeAPIError, match="explicit reconciliation is required"):
        await NodeOperation._start_or_attach_node(
            runtime,
            SimpleNamespace(name="node", keep_alive=30),
            SimpleNamespace(type=object(), to_str=lambda: "{}"),
            [],
            object(),
            force_start=True,
        )

    runtime.stop.assert_not_awaited()
    runtime.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_force_start_stop_timeout_does_not_attach_unknown_old_runtime():
    unknown_stop = SimpleNamespace(
        operation=LifecycleOperation.STOP,
        observed=LifecycleStatus.STOPPING,
        desired=LifecycleStatus.STOPPED,
    )
    runtime = SimpleNamespace(
        node_id="bridge-3",
        _lifecycle_coordinator=None,
        get_lifecycle_state=AsyncMock(side_effect=[None, unknown_stop]),
        info=AsyncMock(return_value=SimpleNamespace(user_sync_epoch_supported=True)),
        stop=AsyncMock(side_effect=NodeAPIError(-1, "Request timed out")),
        start=AsyncMock(),
        connect=AsyncMock(),
    )
    result = await NodeOperation._connect_runtime(
        runtime,
        SimpleNamespace(id=3, name="node", status=NodeStatus.connected, keep_alive=30),
        SimpleNamespace(type=object(), to_str=lambda: "{}"),
        [],
        set(),
        force_start=True,
    )

    assert result["status"] is NodeStatus.error
    assert result["message"] == "Request timed out"
    runtime.start.assert_not_awaited()
    runtime.connect.assert_not_awaited()
