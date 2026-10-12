"""Node lifecycle operations versus in-flight user syncs.

A connection change or a removal preempts a running sync, while an unchanged
health-check reconnect and a metadata-only edit (name, usage coefficient) let it
finish so pending user deltas are not dropped.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.db.models import Node, NodeStatus
from app.node import NodeManager, UserSyncPreemptedError
from app.operation import OperatorType, node as node_operation_module
from app.operation.node import NodeOperation

TIMEOUT = 1


class _FakePGNode:
    """Bridge stand-in whose deliveries block on ``gate`` while it is set."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.name = kwargs.get("name")
        self.chunked = True
        self.gate: asyncio.Event | None = None
        self.entered = asyncio.Event()
        self.delivered: list[list] = []
        self.full_syncs: list[list] = []
        self.stop_calls = 0

    async def get_extra(self):
        return self.kwargs.get("extra", {})

    async def set_health(self, health):
        pass

    async def stop(self, timeout=None):
        self.stop_calls += 1

    async def _wait_gate(self):
        self.entered.set()
        if self.gate is not None:
            await self.gate.wait()

    async def _supports_chunked_sync(self):
        return self.chunked, "0.5.2"

    async def sync_users_chunked(self, batch, chunk_size, flush_pending):
        await self._wait_gate()
        self.delivered.append(list(batch))
        return []

    async def _sync_batch_users(self, batch):
        # Per-user fallback: on a stuck node every send waits for its own timeout.
        await self._wait_gate()
        self.delivered.append(list(batch))
        return []

    async def sync_users(self, users, flush_pending=False):
        await self._wait_gate()
        self.full_syncs.append(list(users))


def _make_node(node_id: int, **overrides) -> Node:
    defaults = {
        "name": "n1",
        "address": "10.0.0.1",
        "port": 1000,
        "api_port": 1001,
        "server_ca": "ca",
        "api_key": "key",
        "core_config_id": None,
        "usage_coefficient": 1.0,
    }
    defaults.update(overrides)
    node = Node(**defaults)
    node.id = node_id
    return node


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> NodeManager:
    monkeypatch.setattr("app.node.ensure_bridge_memory", AsyncMock(return_value=None))
    monkeypatch.setattr("app.node.get_bridge_memory", lambda: (None, None, None))
    monkeypatch.setattr("app.node.create_node", lambda **kwargs: _FakePGNode(**kwargs))
    monkeypatch.setattr("app.node.nats_settings.node_update_users_batch_size", 2)
    manager = NodeManager()
    manager.logger = MagicMock()
    return manager


async def _settle():
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_remove_node_cancels_stuck_per_user_fallback(manager: NodeManager):
    """Without chunked sync support the bridge sends users one by one, and a stuck node makes
    every send wait for its timeout. Removing the node must not queue behind that delivery."""
    node = await manager.update_node(_make_node(1))
    node.chunked = False
    node.gate = asyncio.Event()  # never released: the node is stuck

    sync = asyncio.create_task(manager._update_users([object() for _ in range(4)]))
    await asyncio.wait_for(node.entered.wait(), TIMEOUT)

    await asyncio.wait_for(manager.remove_node(1, remote_stop=False), TIMEOUT)
    await asyncio.wait_for(sync, TIMEOUT)

    assert await manager.get_node(1) is None
    assert node.delivered == []
    assert manager._user_sync_tasks == {}
    # The cancelled delivery is logged for diagnosis, not reported as a failure.
    manager.logger.debug.assert_called_once()
    manager.logger.error.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["full", "bulk"])
async def test_unchanged_reconnect_keeps_sync_but_connection_change_cancels_it(manager: NodeManager, kind: str):
    node = await manager.update_node(_make_node(1))
    node.gate = asyncio.Event()
    users = [object() for _ in range(4)]
    if kind == "full":
        sync = asyncio.create_task(manager.sync_full(1, users))
    else:
        sync = asyncio.create_task(manager._update_users(users))
    await asyncio.wait_for(node.entered.wait(), TIMEOUT)

    # The health-check watchdog reconnects with an unchanged config: it reuses the
    # live object at once and leaves the running sync alone.
    assert await asyncio.wait_for(manager.update_node(_make_node(1)), TIMEOUT) is node
    await _settle()
    assert not sync.done()
    assert node.stop_calls == 0

    # A real connection change preempts the sync instead of waiting behind it.
    replacement = await asyncio.wait_for(manager.update_node(_make_node(1, address="10.0.0.2")), TIMEOUT)
    assert replacement is not node
    assert node.stop_calls == 1

    if kind == "full":
        # Only the sync is cancelled; its caller gets a clear error instead.
        with pytest.raises(UserSyncPreemptedError):
            await asyncio.wait_for(sync, TIMEOUT)
        assert node.full_syncs == []
    else:
        await asyncio.wait_for(sync, TIMEOUT)
        assert node.delivered == []
        assert replacement.delivered == []
    assert manager._user_sync_tasks == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"name": "renamed"}, {"usage_coefficient": 2.0}])
async def test_metadata_edit_keeps_bulk_deltas(manager: NodeManager, change: dict):
    """A metadata-only edit replaces the bridge object but must not drop pending deltas:
    nothing would re-send them once such edits no longer restart the node. It waits for
    the batch in flight and the remaining batches go to the replacement object."""
    node = await manager.update_node(_make_node(1))
    node.gate = asyncio.Event()
    users = [object() for _ in range(4)]
    sync = asyncio.create_task(manager._update_users(users))
    await asyncio.wait_for(node.entered.wait(), TIMEOUT)

    edit = asyncio.create_task(manager.update_node(_make_node(1, **change)))
    await _settle()
    assert not edit.done()
    assert not sync.done()

    node.gate.set()
    replacement = await asyncio.wait_for(edit, TIMEOUT)
    await asyncio.wait_for(sync, TIMEOUT)

    assert replacement is not node
    assert node.delivered == [users[:2]]
    assert replacement.delivered == [users[2:]]
    manager.logger.debug.assert_not_called()
    manager.logger.error.assert_not_called()


@pytest.mark.asyncio
async def test_metadata_edit_waits_for_full_sync(manager: NodeManager):
    node = await manager.update_node(_make_node(1))
    node.gate = asyncio.Event()
    users = [object()]
    sync = asyncio.create_task(manager.sync_full(1, users))
    await asyncio.wait_for(node.entered.wait(), TIMEOUT)

    edit = asyncio.create_task(manager.update_node(_make_node(1, name="renamed")))
    await _settle()
    assert not edit.done()

    node.gate.set()
    assert await asyncio.wait_for(sync, TIMEOUT) is node
    assert await asyncio.wait_for(edit, TIMEOUT) is not node
    assert node.full_syncs == [users]


@pytest.mark.asyncio
async def test_remove_node_preempts_full_sync_without_cancelling_caller(manager: NodeManager):
    node = await manager.update_node(_make_node(1))
    node.gate = asyncio.Event()
    sync = asyncio.create_task(manager.sync_full(1, [object()]))
    await asyncio.wait_for(node.entered.wait(), TIMEOUT)

    await asyncio.wait_for(manager.remove_node(1, remote_stop=False), TIMEOUT)

    with pytest.raises(UserSyncPreemptedError):
        await asyncio.wait_for(sync, TIMEOUT)
    assert node.full_syncs == []
    assert manager._user_sync_tasks == {}


@pytest.mark.asyncio
async def test_cancelling_full_sync_caller_cancels_the_sync(manager: NodeManager):
    node = await manager.update_node(_make_node(1))
    node.gate = asyncio.Event()
    sync = asyncio.create_task(manager.sync_full(1, [object()]))
    await asyncio.wait_for(node.entered.wait(), TIMEOUT)
    (child,) = manager._user_sync_tasks[1]

    sync.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sync

    assert child.cancelled()
    assert manager._user_sync_tasks == {}
    # The per-node lock was released with the cancelled sync.
    assert await asyncio.wait_for(manager.update_node(_make_node(1, name="renamed")), TIMEOUT) is not node


@pytest.mark.asyncio
async def test_sync_node_users_maps_preemption_to_conflict(monkeypatch: pytest.MonkeyPatch):
    operator = NodeOperation(operator_type=OperatorType.API)
    db_node = SimpleNamespace(id=5, status=NodeStatus.connected, core_config_id=None)
    monkeypatch.setattr(operator, "get_validated_node", AsyncMock(return_value=db_node))
    monkeypatch.setattr(operator, "_get_core_users_map", AsyncMock(return_value=({}, {1: []})))
    monkeypatch.setattr(node_operation_module.node_manager, "get_node", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        node_operation_module.node_manager,
        "sync_full",
        AsyncMock(side_effect=UserSyncPreemptedError("preempted")),
    )
    update_status = AsyncMock()
    monkeypatch.setattr(node_operation_module, "update_node_status", update_status)

    with pytest.raises(HTTPException) as exc_info:
        await operator._sync_node_users_local(object(), 5, True)

    assert exc_info.value.status_code == 409
    # Preemption is not a node fault: the node keeps its status.
    update_status.assert_not_awaited()
