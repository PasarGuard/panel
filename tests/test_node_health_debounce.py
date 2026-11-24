from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PasarGuardNodeBridge import Health

from app.db.models import NodeStatus
from app.jobs import node_checker
from app.models.settings import General, NodeHealthSettings
from app.operation.node import NodeOperation

TIMEOUT = (Health.BROKEN, -1, "Health check timeout")
DEAD_CORE = (Health.BROKEN, 500, "backend not initialized")
HEALTHY = (Health.HEALTHY, None, None)


def _patch_health_settings(monkeypatch, **values):
    """Serve `general.node_health` from memory; tests change the returned object in place."""
    health = NodeHealthSettings.model_construct(**{**NodeHealthSettings().model_dump(), **values})
    general = General.model_construct(node_health=health)

    async def get_general_settings():
        return general

    monkeypatch.setattr(node_checker, "general_settings", get_general_settings)
    return health


class _FakeDB:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *args):
        return False


def _make_node():
    node = MagicMock()
    node.requires_hard_reset.return_value = False
    node.get_lifecycle_state = AsyncMock(return_value=None)
    node.update_observed_lifecycle = AsyncMock()
    node.get_health = AsyncMock(return_value=Health.HEALTHY)
    node.set_health = AsyncMock()
    node.get_versions = AsyncMock(return_value=("0.5.4", "26.3.27"))
    node.info = AsyncMock(return_value=SimpleNamespace(started=True, node_version="0.5.4", core_version="26.3.27"))
    node.set_reported_versions = AsyncMock()
    return node


@pytest.fixture
def checker(monkeypatch):
    monkeypatch.setattr(node_checker, "_health_streaks", {})
    health = _patch_health_settings(monkeypatch, fail_threshold=3, recover_threshold=2)
    monkeypatch.setattr(node_checker, "_owns_health_checks", lambda: True)
    monkeypatch.setattr(node_checker, "needs_shared_bridge_memory", lambda: False)
    monkeypatch.setattr(node_checker, "GetDB", lambda: _FakeDB())
    monkeypatch.setattr(node_checker, "get_bridge_memory", lambda: (None, None, None))
    monkeypatch.setattr(node_checker.notification, "recovered_node", AsyncMock())
    update_status = AsyncMock(return_value=True)
    monkeypatch.setattr(NodeOperation, "_update_single_node_status", update_status)
    repair = AsyncMock()
    monkeypatch.setattr(node_checker.node_operator, "connect_single_node", repair)
    probe = AsyncMock()
    monkeypatch.setattr(node_checker, "verify_node_backend_health", probe)

    async def run(db_node, node, *results):
        for result in results:
            probe.return_value = result
            await node_checker.process_node_health_check(db_node, node)

    return SimpleNamespace(run=run, update_status=update_status, repair=repair, monkeypatch=monkeypatch, health=health)


def _db_node(status=NodeStatus.connected):
    return SimpleNamespace(id=7, name="debounced", status=status, default_timeout=10)


def _written_statuses(update_status):
    return [call.args[2] for call in update_status.await_args_list]


@pytest.mark.asyncio
async def test_failures_below_threshold_keep_the_node_connected(checker):
    db_node, node = _db_node(), _make_node()

    await checker.run(db_node, node, TIMEOUT, TIMEOUT)
    checker.update_status.assert_not_awaited()
    node.set_health.assert_not_awaited()

    await checker.run(db_node, node, TIMEOUT)
    assert _written_statuses(checker.update_status) == [NodeStatus.error]
    assert checker.update_status.await_args.kwargs["expected_status"] is NodeStatus.connected
    node.set_health.assert_awaited_once_with(Health.BROKEN)


@pytest.mark.asyncio
async def test_a_good_probe_restarts_the_failure_streak(checker):
    db_node, node = _db_node(), _make_node()

    await checker.run(db_node, node, TIMEOUT, TIMEOUT, HEALTHY, TIMEOUT, TIMEOUT)

    checker.update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_errored_node_needs_consecutive_good_probes_to_recover(checker):
    db_node, node = _db_node(NodeStatus.error), _make_node()

    await checker.run(db_node, node, HEALTHY)
    checker.update_status.assert_not_awaited()

    await checker.run(db_node, node, HEALTHY)
    assert _written_statuses(checker.update_status) == [NodeStatus.connected]
    assert checker.update_status.await_args.kwargs["expected_status"] is NodeStatus.error
    node_checker.notification.recovered_node.assert_awaited_once()


@pytest.mark.asyncio
async def test_recovery_uses_live_versions_after_node_restart(checker):
    db_node, node = _db_node(NodeStatus.connecting), _make_node()
    node.info.return_value = SimpleNamespace(started=True, node_version="0.5.5", core_version="26.10.21")

    await checker.run(db_node, node, HEALTHY, HEALTHY)

    assert checker.update_status.await_args.kwargs["node_version"] == "0.5.5"
    assert checker.update_status.await_args.kwargs["xray_version"] == "26.10.21"
    node.set_reported_versions.assert_awaited_once_with("0.5.5", "26.10.21")
    node.get_versions.assert_not_awaited()


@pytest.mark.asyncio
async def test_streak_restarts_for_a_replaced_node_object(checker):
    db_node = _db_node()

    await checker.run(db_node, _make_node(), TIMEOUT, TIMEOUT)
    await checker.run(db_node, _make_node(), TIMEOUT)

    checker.update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_streak_restarts_when_the_stored_status_changes(checker):
    db_node, node = _db_node(), _make_node()

    await checker.run(db_node, node, TIMEOUT, TIMEOUT)
    db_node.status = NodeStatus.connecting
    await checker.run(db_node, node, TIMEOUT)

    checker.update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_followers_never_write_status_or_repair(checker):
    checker.monkeypatch.setattr(node_checker, "_owns_health_checks", lambda: False)
    connected, errored = _db_node(), SimpleNamespace(id=8, name="errored", status=NodeStatus.error, default_timeout=10)

    await checker.run(connected, _make_node(), *[DEAD_CORE] * 5)
    await checker.run(errored, _make_node(), *[HEALTHY] * 3)

    checker.update_status.assert_not_awaited()
    checker.repair.assert_not_awaited()


@pytest.mark.asyncio
async def test_dead_core_is_repaired_before_the_failure_threshold(checker):
    db_node, node = _db_node(), _make_node()

    await checker.run(db_node, node, DEAD_CORE)

    checker.repair.assert_awaited_once()
    assert checker.repair.await_args.kwargs == {"health_check": True}
    checker.update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_thresholds_of_one_react_to_a_single_probe(checker):
    checker.health.fail_threshold = 1
    checker.health.recover_threshold = 1
    db_node, node = _db_node(), _make_node()

    await checker.run(db_node, node, TIMEOUT)
    db_node.status = NodeStatus.error
    await checker.run(db_node, node, HEALTHY)

    assert _written_statuses(checker.update_status) == [NodeStatus.error, NodeStatus.connected]
