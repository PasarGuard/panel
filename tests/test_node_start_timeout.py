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
    )
    pg_node = SimpleNamespace(
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
    state = SimpleNamespace(observed=LifecycleStatus.BROKEN, desired=LifecycleStatus.HEALTHY)
    pg_node = SimpleNamespace(get_lifecycle_state=AsyncMock(return_value=state), start=AsyncMock())
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
    pg_node.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_connect_node_attaches_when_remote_start_finishes_after_timeout(monkeypatch: pytest.MonkeyPatch):
    pg_node = object()
    db_node = SimpleNamespace(id=19, name="slow-node", status=NodeStatus.connecting)
    core = SimpleNamespace(type=object())
    attached = SimpleNamespace(node_version="0.5.4", core_version="1.0.20260223")

    monkeypatch.setattr(node_operation_module.node_manager, "get_node", AsyncMock(return_value=pg_node))
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


@pytest.mark.asyncio
async def test_health_check_attaches_ambiguous_timed_out_start_before_reconnect(monkeypatch: pytest.MonkeyPatch):
    state = SimpleNamespace(observed=LifecycleStatus.BROKEN, desired=LifecycleStatus.HEALTHY)
    node = MagicMock()
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
