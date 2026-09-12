from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PasarGuardNodeBridge import Health, NodeAPIError
from PasarGuardNodeBridge.storage import LifecycleStatus
from pydantic import ValidationError

from app.db.models import NodeStatus
from app.jobs import node_checker
from app.models.node import NodeModify
from app.operation import node as node_operation_module
from app.operation.node import NodeOperation


def _patch_locked_runtime(monkeypatch: pytest.MonkeyPatch, pg_node):
    calls: list[int] = []

    @asynccontextmanager
    async def locked_runtime(node_id: int):
        calls.append(node_id)
        yield pg_node

    monkeypatch.setattr(node_operation_module.node_manager, "locked_runtime", locked_runtime)
    return calls


def test_default_timeout_allows_slow_node_startup():
    assert NodeModify(default_timeout=300).default_timeout == 300

    with pytest.raises(ValidationError):
        NodeModify(default_timeout=2)


@pytest.mark.asyncio
async def test_attach_requires_remote_core_to_be_started():
    state = SimpleNamespace(
        observed=LifecycleStatus.BROKEN,
        desired=LifecycleStatus.HEALTHY,
        epoch=1,
        operation=None,
    )
    pg_node = SimpleNamespace(
        node_id="slow-node-namespace",
        get_lifecycle_state=AsyncMock(return_value=state),
        info=AsyncMock(
            return_value=SimpleNamespace(
                started=False,
                node_version="0.5.4",
                core_version="1.0.20260223",
            )
        ),
        connect=AsyncMock(),
    )

    assert await NodeOperation._attach_if_running(pg_node, "slow-node") is None
    pg_node.connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_or_attach_probes_broken_desired_healthy_lifecycle(monkeypatch: pytest.MonkeyPatch):
    state = SimpleNamespace(observed=LifecycleStatus.BROKEN, desired=LifecycleStatus.HEALTHY, operation=None)
    pg_node = SimpleNamespace(
        node_id="slow-node-namespace",
        get_lifecycle_state=AsyncMock(return_value=state),
        reconcile_users=AsyncMock(),
        start=AsyncMock(),
    )
    attached = object()
    attach = AsyncMock(return_value=attached)
    monkeypatch.setattr(NodeOperation, "_attach_if_running", attach)

    result = await NodeOperation._start_or_attach_node(
        pg_node,
        SimpleNamespace(name="slow-node"),
        object(),
        [],
        object(),
    )

    assert result is attached
    attach.assert_awaited_once_with(pg_node, "slow-node")
    pg_node.reconcile_users.assert_awaited_once_with([])
    pg_node.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_force_start_skips_attach_and_starts_core(monkeypatch: pytest.MonkeyPatch):
    started = SimpleNamespace(node_version="0.5.4", core_version="26.3.27")
    pg_node = SimpleNamespace(
        node_id="england-namespace",
        get_lifecycle_state=AsyncMock(return_value=None),
        info=AsyncMock(return_value=SimpleNamespace(user_sync_epoch_supported=True)),
        start=AsyncMock(return_value=started),
        stop=AsyncMock(),
    )
    attach = AsyncMock(return_value=object())
    monkeypatch.setattr(NodeOperation, "_attach_if_running", attach)
    db_node = SimpleNamespace(name="england", keep_alive=60)
    core = SimpleNamespace(type=None, to_str=lambda: "{}", exclude_inbound_tags=[])

    result = await NodeOperation._start_or_attach_node(
        pg_node,
        db_node,
        core,
        [],
        object(),
        force_start=True,
    )

    assert result is started
    attach.assert_not_awaited()
    pg_node.stop.assert_awaited_once()
    pg_node.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_node_attaches_when_remote_start_finishes_after_timeout(monkeypatch: pytest.MonkeyPatch):
    pg_node = SimpleNamespace(node_id="slow-node-namespace", reconcile_users=AsyncMock())
    db_node = SimpleNamespace(id=19, name="slow-node", status=NodeStatus.connecting)
    core = SimpleNamespace(type=object())
    attached = SimpleNamespace(node_version="0.5.4", core_version="1.0.20260223")

    runtime_calls = _patch_locked_runtime(monkeypatch, pg_node)
    monkeypatch.setattr(
        NodeOperation,
        "_start_or_attach_node",
        AsyncMock(side_effect=NodeAPIError(-1, "Request timed out")),
    )
    attach = AsyncMock(return_value=attached)
    monkeypatch.setattr(NodeOperation, "_attach_if_running", attach)

    result = await NodeOperation.connect_node(db_node, core, [])

    assert result == {
        "node_id": 19,
        "status": NodeStatus.connected,
        "message": "",
        "xray_version": "1.0.20260223",
        "node_version": "0.5.4",
        "old_status": NodeStatus.connecting,
    }
    attach.assert_awaited_once_with(pg_node, "slow-node")
    assert runtime_calls == [19]
    pg_node.reconcile_users.assert_awaited_once_with([])


@pytest.mark.asyncio
async def test_health_check_attaches_ambiguous_timed_out_start_before_reconnect(monkeypatch: pytest.MonkeyPatch):
    state = SimpleNamespace(observed=LifecycleStatus.BROKEN, desired=LifecycleStatus.HEALTHY)
    node = MagicMock()
    node._extra = {}
    node.requires_hard_reset.return_value = False
    node.get_lifecycle_state = AsyncMock(return_value=state)
    db_node = SimpleNamespace(id=19, name="slow-node", status=NodeStatus.error)

    monkeypatch.setattr(
        node_checker,
        "verify_node_backend_health",
        AsyncMock(return_value=(Health.NOT_CONNECTED, None, None)),
    )
    attach = AsyncMock(return_value=object())
    monkeypatch.setattr(NodeOperation, "_attach_if_running", attach)
    reconnect = AsyncMock()
    monkeypatch.setattr(node_checker.node_operator, "connect_single_node", reconnect)

    await node_checker.process_node_health_check(db_node, node)

    attach.assert_awaited_once_with(node, "slow-node")
    reconnect.assert_not_awaited()


class _FakeDB:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *args):
        return False


def _patch_health_check_db(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(node_checker, "GetDB", lambda: _FakeDB())
    monkeypatch.setattr(NodeOperation, "_update_single_node_status", AsyncMock())
    monkeypatch.setattr(node_checker, "get_bridge_memory", lambda: (None, None, None))


@pytest.mark.asyncio
async def test_health_check_reapplies_config_when_keep_alive_stopped_core(monkeypatch: pytest.MonkeyPatch):
    """pg-node keep-alive stops Xray but leaves HTTP up. Panel must POST /start again."""
    node = MagicMock()
    node._extra = {}
    node.requires_hard_reset.return_value = False
    node.get_lifecycle_state = AsyncMock(return_value=None)
    node.update_observed_lifecycle = AsyncMock()
    db_node = SimpleNamespace(id=19, name="dead-core", status=NodeStatus.connected)

    _patch_health_check_db(monkeypatch)
    monkeypatch.setattr(
        node_checker,
        "verify_node_backend_health",
        AsyncMock(return_value=(Health.BROKEN, 500, "backend not initialized")),
    )
    reconnect = AsyncMock()
    monkeypatch.setattr(node_checker.node_operator, "connect_single_node", reconnect)

    await node_checker.process_node_health_check(db_node, node)

    reconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_check_waits_when_core_not_started_during_in_flight_start(monkeypatch: pytest.MonkeyPatch):
    node = MagicMock()
    node._extra = {}
    node.requires_hard_reset.return_value = False
    node.get_lifecycle_state = AsyncMock(return_value=None)
    node.update_observed_lifecycle = AsyncMock()
    db_node = SimpleNamespace(id=19, name="starting-node", status=NodeStatus.connected)

    _patch_health_check_db(monkeypatch)
    NodeOperation._in_flight_connects.add(19)
    monkeypatch.setattr(
        node_checker,
        "verify_node_backend_health",
        AsyncMock(return_value=(Health.BROKEN, 500, "backend not initialized")),
    )
    reconnect = AsyncMock()
    monkeypatch.setattr(node_checker.node_operator, "connect_single_node", reconnect)

    try:
        await node_checker.process_node_health_check(db_node, node)
    finally:
        NodeOperation._in_flight_connects.discard(19)

    reconnect.assert_not_awaited()


def test_should_reconnect_skips_core_not_started_500():
    assert node_checker.should_reconnect_after_health_error(500, "core is not started yet") is False
    assert node_checker.is_core_not_started_error(500, "core is not started yet") is True
    assert node_checker.is_core_starting_error(503, "core is not started yet") is True
    assert node_checker.is_core_dead_error(500, "backend not initialized") is True
    assert node_checker.should_reconnect_after_health_error(500, "backend not initialized") is False
    assert node_checker.should_reconnect_after_health_error(400, "bad request") is True


@pytest.mark.asyncio
async def test_health_check_waits_when_core_is_still_starting(monkeypatch: pytest.MonkeyPatch):
    """pg-node still has a backend object; another Start would kill that process."""
    node = MagicMock()
    node._extra = {}
    node.requires_hard_reset.return_value = False
    node.get_lifecycle_state = AsyncMock(return_value=None)
    node.update_observed_lifecycle = AsyncMock()
    db_node = SimpleNamespace(id=19, name="starting-core", status=NodeStatus.connected)

    _patch_health_check_db(monkeypatch)
    monkeypatch.setattr(
        node_checker,
        "verify_node_backend_health",
        AsyncMock(return_value=(Health.BROKEN, 503, "core is not started yet")),
    )
    reconnect = AsyncMock()
    monkeypatch.setattr(node_checker.node_operator, "connect_single_node", reconnect)

    await node_checker.process_node_health_check(db_node, node)

    reconnect.assert_not_awaited()


@pytest.mark.asyncio
async def test_connect_node_delegates_running_core_decision_to_lifecycle_path(monkeypatch: pytest.MonkeyPatch):
    pg_node = SimpleNamespace(
        node_id="hetz-tunnel-namespace",
        get_health=AsyncMock(return_value=Health.HEALTHY),
        get_versions=AsyncMock(return_value=("0.5.4", "26.3.27")),
        start=AsyncMock(),
    )
    db_node = SimpleNamespace(id=3, name="Hetz Tunnel", status=NodeStatus.connected)
    runtime_calls = _patch_locked_runtime(monkeypatch, pg_node)
    start_or_attach = AsyncMock(return_value=None)
    monkeypatch.setattr(NodeOperation, "_start_or_attach_node", start_or_attach)

    result = await NodeOperation.connect_node(db_node, SimpleNamespace(type=None), [])

    assert result is None
    assert runtime_calls == [3]
    start_or_attach.assert_awaited_once()
    pg_node.start.assert_not_awaited()
