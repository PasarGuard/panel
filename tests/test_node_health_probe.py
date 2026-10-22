"""Health-check cost of unreachable nodes: probe timeout, backoff and the never-connected path."""

import asyncio
import collections
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import certifi
import pytest
from PasarGuardNodeBridge import Health, NodeAPIError, NodeType

from app.db.models import CoreType, NodeStatus
from app.jobs import node_checker
from app.node import heartbeat as heartbeat_module
from app.node.bridge import create_node
from app.operation import node as node_operation
from app.operation.node import NodeOperation

TIMEOUT = (Health.BROKEN, -1, "Health check timeout")
HEALTHY = (Health.HEALTHY, None, None)


class _HangingStub:
    """gRPC stub of a node whose packets are dropped: every RPC waits forever."""

    def __init__(self):
        self.calls = collections.Counter()

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        async def rpc(_request, metadata=None):
            self.calls[name] += 1
            await asyncio.sleep(3600)

        return rpc


class _FakeDB:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *args):
        return False


def _real_node(name: str):
    node = create_node(
        connection=NodeType.grpc,
        address="127.0.0.1",
        port=1,
        api_port=1,
        server_ca=certifi.contents(),
        api_key=str(uuid4()),
        name=name,
        node_id=f"probe-{uuid4()}",
        default_timeout=30,
        internal_timeout=30,
    )
    stub = _HangingStub()
    node._client = stub
    return node, stub


def _db_node(status=NodeStatus.error, **extra):
    return SimpleNamespace(
        id=41, name="far-away", status=status, core_config_id=1, keep_alive=60, default_timeout=30, **extra
    )


@pytest.fixture
def checker(monkeypatch):
    monkeypatch.setattr(node_checker, "_health_streaks", {})
    monkeypatch.setattr(node_checker, "_probe_backoffs", {})
    monkeypatch.setattr(node_checker.job_settings, "node_health_fail_threshold", 3)
    monkeypatch.setattr(node_checker.job_settings, "node_health_recover_threshold", 2)
    monkeypatch.setattr(node_checker.job_settings, "core_health_check_interval", 10)
    monkeypatch.setattr(node_checker.job_settings, "node_health_probe_timeout", 0.2)
    monkeypatch.setattr(node_checker.job_settings, "node_health_max_backoff", 60)
    monkeypatch.setattr(node_checker, "_owns_health_checks", lambda: True)
    monkeypatch.setattr(node_checker, "needs_shared_bridge_memory", lambda: False)
    monkeypatch.setattr(node_checker, "GetDB", lambda: _FakeDB())
    monkeypatch.setattr(node_checker, "get_bridge_memory", lambda: (None, None, None))
    monkeypatch.setattr(node_checker.notification, "recovered_node", AsyncMock())
    monkeypatch.setattr(NodeOperation, "_update_single_node_status", AsyncMock(return_value=True))
    clock = [1000.0]
    monkeypatch.setattr(node_checker, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    return SimpleNamespace(monkeypatch=monkeypatch, clock=clock)


def _fake_node(health=Health.BROKEN):
    node = MagicMock()
    node.requires_hard_reset.return_value = False
    node.get_lifecycle_state = AsyncMock(return_value=None)
    node.update_observed_lifecycle = AsyncMock()
    node.get_health = AsyncMock(return_value=health)
    node.set_health = AsyncMock()
    node.get_versions = AsyncMock(return_value=("0.5.4", "26.10.21"))
    node.info = AsyncMock(return_value=SimpleNamespace(started=True, node_version="0.5.4", core_version="26.10.21"))
    return node


async def _runs(checker, db_node, node, seconds, step=10):
    """Run the per-node check once per interval and return when it probed."""
    probe = node_checker.verify_node_backend_health
    probed = []
    start = checker.clock[0]
    for offset in range(0, seconds + 1, step):
        checker.clock[0] = start + offset
        before = probe.await_count
        await node_checker.process_node_health_check(db_node, node)
        if probe.await_count > before:
            probed.append(offset)
    return probed


@pytest.mark.asyncio
async def test_probe_does_not_wait_for_a_raised_default_timeout(checker):
    node, stub = _real_node("slow-link")
    await node.connect("0.5.4", "26.10.21")
    db_node = _db_node(NodeStatus.connected)
    try:
        started = time.monotonic()
        await asyncio.wait_for(node_checker.process_node_health_check(db_node, node), timeout=5)
        assert time.monotonic() - started < 2
        assert stub.calls == {"GetBackendStats": 1}
    finally:
        await node.set_health(Health.INVALID)


@pytest.mark.asyncio
async def test_probe_timeout_is_capped_by_the_node_default_timeout(checker):
    checker.monkeypatch.setattr(node_checker.job_settings, "node_health_probe_timeout", 5)
    node = _fake_node(Health.HEALTHY)
    node.get_backend_stats = AsyncMock()

    await node_checker.process_node_health_check(_db_node(NodeStatus.connected), node)
    assert node.get_backend_stats.await_args.kwargs["timeout"] == 5

    db_node = _db_node(NodeStatus.connected)
    db_node.default_timeout = 3
    await node_checker.process_node_health_check(db_node, node)
    assert node.get_backend_stats.await_args.kwargs["timeout"] == 3


@pytest.mark.asyncio
async def test_errored_unreachable_node_is_probed_with_backoff(checker):
    checker.monkeypatch.setattr(node_checker, "verify_node_backend_health", AsyncMock(return_value=TIMEOUT))

    probed = await _runs(checker, _db_node(), _fake_node(), 180)

    assert probed == [0, 20, 60, 120, 180]


@pytest.mark.asyncio
async def test_backoff_can_be_disabled(checker):
    checker.monkeypatch.setattr(node_checker.job_settings, "node_health_max_backoff", 0)
    checker.monkeypatch.setattr(node_checker, "verify_node_backend_health", AsyncMock(return_value=TIMEOUT))

    probed = await _runs(checker, _db_node(), _fake_node(), 60)

    assert probed == [0, 10, 20, 30, 40, 50, 60]


@pytest.mark.asyncio
async def test_failure_threshold_still_counts_every_run(checker):
    """Backoff starts only once the node is reported as error, so the debounce timing is unchanged."""
    checker.monkeypatch.setattr(node_checker, "verify_node_backend_health", AsyncMock(return_value=TIMEOUT))

    probed = await _runs(checker, _db_node(NodeStatus.connected), _fake_node(Health.HEALTHY), 40)

    assert probed == [0, 10, 20, 30, 40]


@pytest.mark.asyncio
async def test_a_good_probe_ends_the_backoff(checker):
    probe = AsyncMock(return_value=TIMEOUT)
    checker.monkeypatch.setattr(node_checker, "verify_node_backend_health", probe)
    db_node, node = _db_node(), _fake_node()

    assert await _runs(checker, db_node, node, 60) == [0, 20, 60]
    probe.return_value = HEALTHY
    checker.clock[0] += 60
    # Recovery needs two good probes in a row; the second one must not wait.
    assert await _runs(checker, db_node, node, 10) == [0, 10]
    assert NodeOperation._update_single_node_status.await_args.args[2] is NodeStatus.connected


@pytest.mark.asyncio
async def test_backoff_counts_from_when_the_check_gets_a_slot(checker):
    probe = AsyncMock(return_value=TIMEOUT)
    checker.monkeypatch.setattr(node_checker, "verify_node_backend_health", probe)
    slots = asyncio.Semaphore(1)
    checker.monkeypatch.setattr(node_checker, "NODE_CHECK_SEM", slots)
    db_node, node = _db_node(), _fake_node()

    await slots.acquire()
    check = asyncio.create_task(node_checker.process_node_health_check(db_node, node))
    await asyncio.sleep(0)
    # Other nodes hold every check slot for 15 s.
    checker.clock[0] += 15
    slots.release()
    await check
    assert probe.await_count == 1

    # The 20 s backoff starts at the probe, not when the run queued the check.
    checker.clock[0] += 10
    await node_checker.process_node_health_check(db_node, node)
    assert probe.await_count == 1
    checker.clock[0] += 10
    await node_checker.process_node_health_check(db_node, node)
    assert probe.await_count == 2


@pytest.fixture
def heartbeat(checker):
    """The process heartbeat, beating node 41 on the checker's clock."""
    beater = heartbeat_module.node_heartbeat
    nodes = []
    manager = SimpleNamespace(get_keep_alive_nodes=AsyncMock(side_effect=lambda: [(41, node, 60) for node in nodes]))
    checker.monkeypatch.setattr(beater, "_manager", manager)
    checker.monkeypatch.setattr(beater, "_due", {})
    checker.monkeypatch.setattr(beater, "_beats", {})
    checker.monkeypatch.setattr(beater, "_answers", {})
    checker.monkeypatch.setattr(heartbeat_module, "needs_job_leader", lambda: False)
    checker.monkeypatch.setattr(heartbeat_module, "time", node_checker.time)

    async def beat(node):
        nodes[:] = [node]
        await beater.tick()
        for _ in range(3):
            await asyncio.sleep(0)

    return beat


def _unreachable(checker, kind):
    """An errored node whose health check gets no reply, and the switch that brings its link back."""
    link = [False]
    if kind == "timed_out":
        # The probe reply is lost, as on a lossy link.
        node, probed = _fake_node(), TIMEOUT
    else:
        # Never connected: only the reachability probe goes out.
        node, probed = _fake_node(Health.NOT_CONNECTED), (Health.NOT_CONNECTED, None, None)
    answer = node.info.return_value

    async def info(timeout=None):
        if not link[0]:
            raise NodeAPIError(-1, "Request timed out")
        return answer

    node.info = AsyncMock(side_effect=info)
    checker.monkeypatch.setattr(node_checker, "verify_node_backend_health", AsyncMock(return_value=probed))
    return node, link


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["timed_out", "never_connected"])
async def test_a_heartbeat_answer_ends_the_backoff_of_an_unreachable_node(checker, heartbeat, kind):
    repair = AsyncMock()
    checker.monkeypatch.setattr(node_checker.node_operator, "connect_single_node", repair)
    db_node, (node, link) = _db_node(), _unreachable(checker, kind)
    assert await _runs(checker, db_node, node, 60) == [0, 20, 60]
    start = checker.clock[0]

    # Next probe due at +60; the link is back and answers a heartbeat at +15.
    checker.clock[0] = start + 10
    assert await _runs(checker, db_node, node, 0) == []
    checker.clock[0] = start + 15
    link[0] = True
    await heartbeat(node)
    checker.clock[0] = start + 20
    assert await _runs(checker, db_node, node, 0) == [0]

    # The probe still decides: it failed again, and the older answer does not end the new backoff.
    checker.clock[0] = start + 30
    assert await _runs(checker, db_node, node, 0) == []
    if kind == "never_connected":
        # Reachable again, so this run tried to start it.
        repair.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["failed_start", "dead_core"])
async def test_a_heartbeat_answer_keeps_the_backoff_of_a_node_that_answered(checker, heartbeat, kind):
    """A node that replies but cannot be repaired gains nothing from more attempts."""
    checker.monkeypatch.setattr(node_checker.node_operator, "connect_single_node", AsyncMock())
    if kind == "failed_start":
        node, result = _fake_node(Health.NOT_CONNECTED), (Health.NOT_CONNECTED, None, None)
    else:
        node, result = _fake_node(), (Health.BROKEN, 503, "backend not initialized")
    probe = AsyncMock(return_value=result)
    checker.monkeypatch.setattr(node_checker, "verify_node_backend_health", probe)
    db_node = _db_node()

    probed = []
    start = checker.clock[0]
    for offset in range(0, 121, 5):
        checker.clock[0] = start + offset
        await heartbeat(node)
        if offset % 10 == 0:
            before = probe.await_count
            await node_checker.process_node_health_check(db_node, node)
            if probe.await_count > before:
                probed.append(offset)

    assert probed == [0, 20, 60, 120]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "admin_action",
    ["reconnected", "enabled_or_edited", "new_connection"],
)
async def test_admin_actions_do_not_wait_for_the_backoff(checker, admin_action):
    checker.monkeypatch.setattr(node_checker, "verify_node_backend_health", AsyncMock(return_value=TIMEOUT))
    db_node, node = _db_node(), _fake_node()
    assert await _runs(checker, db_node, node, 20) == [0, 20]

    if admin_action == "reconnected":
        db_node.status = NodeStatus.connected
    elif admin_action == "enabled_or_edited":
        db_node.status = NodeStatus.connecting
    else:
        node = _fake_node()
    checker.clock[0] += 10

    assert await _runs(checker, db_node, node, 0) == [0]


@pytest.mark.asyncio
async def test_never_connected_unreachable_node_costs_one_short_probe(checker):
    node, stub = _real_node("never-connected")
    db_node = _db_node()
    users = AsyncMock(return_value=[])
    core = SimpleNamespace(
        type=CoreType.xray, to_str=lambda: "{}", exclude_inbound_tags=[], inbounds=[], protocols=None
    )

    async def core_users_map(db, core_ids, *, lazy=False):
        return {1: core}, {1: users if lazy else await users()}

    checker.monkeypatch.setattr(NodeOperation, "_get_core_users_map", staticmethod(core_users_map))
    checker.monkeypatch.setattr(node_operation, "get_node_by_id", AsyncMock(return_value=db_node))
    checker.monkeypatch.setattr(node_operation, "update_node_status", AsyncMock())
    checker.monkeypatch.setattr(node_operation.node_manager, "update_node", AsyncMock(return_value=node))
    checker.monkeypatch.setattr(node_operation.node_manager, "get_node", AsyncMock(return_value=node))
    checker.monkeypatch.setattr(node_operation.notification, "error_node", AsyncMock())
    try:
        started = time.monotonic()
        await asyncio.wait_for(node_checker.process_node_health_check(db_node, node), timeout=5)
        assert time.monotonic() - started < 2
        assert stub.calls == {"GetBaseInfo": 1}
        users.assert_not_awaited()

        # The next attempts wait for the backoff instead of probing every run.
        checker.clock[0] += 10
        await asyncio.wait_for(node_checker.process_node_health_check(db_node, node), timeout=5)
        assert stub.calls == {"GetBaseInfo": 1}
    finally:
        await node.set_health(Health.INVALID)


@pytest.mark.asyncio
async def test_reachable_never_connected_node_is_still_repaired(checker):
    repair = AsyncMock()
    checker.monkeypatch.setattr(node_checker.node_operator, "connect_single_node", repair)
    checker.monkeypatch.setattr(
        node_checker, "verify_node_backend_health", AsyncMock(return_value=(Health.NOT_CONNECTED, None, None))
    )
    node = _fake_node(Health.NOT_CONNECTED)

    await node_checker.process_node_health_check(_db_node(), node)

    node.info.assert_awaited_once()
    assert node.info.await_args.kwargs["timeout"] == 0.2
    repair.assert_awaited_once()
    assert repair.await_args.kwargs == {"health_check": True}


@pytest.mark.asyncio
async def test_failed_start_on_a_reachable_node_backs_off(checker):
    repair = AsyncMock()
    checker.monkeypatch.setattr(node_checker.node_operator, "connect_single_node", repair)
    checker.monkeypatch.setattr(
        node_checker, "verify_node_backend_health", AsyncMock(return_value=(Health.NOT_CONNECTED, None, None))
    )
    db_node, node = _db_node(), _fake_node(Health.NOT_CONNECTED)

    assert await _runs(checker, db_node, node, 60) == [0, 20, 60]
    assert repair.await_count == 3

    # A Start that finally works resets the schedule.
    async def started(*args, **kwargs):
        node.get_health.return_value = Health.HEALTHY

    repair.side_effect = started
    checker.clock[0] += 60
    await node_checker.process_node_health_check(db_node, node)
    assert repair.await_count == 4
    assert node_checker._probe_backoffs == {}


@pytest.mark.asyncio
async def test_a_follower_backs_off_on_its_own_and_starts_over_as_leader(checker):
    leader = [False]
    checker.monkeypatch.setattr(node_checker, "_owns_health_checks", lambda: leader[0])
    checker.monkeypatch.setattr(node_checker, "verify_node_backend_health", AsyncMock(return_value=TIMEOUT))
    db_node, node = _db_node(), _fake_node()

    assert await _runs(checker, db_node, node, 30) == [0, 20]
    assert node_checker._probe_backoffs[db_node.id].leader is False

    # Winning the leadership probes at once, then backs off as the leader.
    leader[0] = True
    checker.clock[0] += 10
    assert await _runs(checker, db_node, node, 10) == [0]
    assert node_checker._probe_backoffs[db_node.id].leader is True


def _health_run(monkeypatch, check, count=3):
    """node_health_check over `count` connected nodes, each checked by `check`."""
    monkeypatch.setattr(node_checker.job_settings, "core_health_check_interval", 0.5)
    for cache in ("_check_tasks", "_health_streaks", "_probe_backoffs", "_sync_recovery_deadlines"):
        monkeypatch.setattr(node_checker, cache, {})
    monkeypatch.setattr(node_checker, "_node_loop_tasks", [])
    monkeypatch.setattr(node_checker, "GetDB", lambda: _FakeDB())
    db_nodes = [
        SimpleNamespace(id=index, name=f"node-{index}", status=NodeStatus.connected) for index in range(1, count + 1)
    ]
    monkeypatch.setattr(node_checker, "get_nodes", AsyncMock(return_value=(db_nodes, len(db_nodes))))
    nodes = {db_node.id: object() for db_node in db_nodes}
    monkeypatch.setattr(node_checker.node_manager, "get_nodes", AsyncMock(return_value=nodes))
    monkeypatch.setattr(node_checker, "process_node_health_check", check)


@pytest.mark.asyncio
async def test_one_slow_node_does_not_hold_up_the_run(monkeypatch):
    release = asyncio.Event()
    checked = collections.Counter()

    async def check(db_node, node):
        checked[db_node.id] += 1
        if db_node.id == 1:
            await release.wait()

    _health_run(monkeypatch, check)
    try:
        await asyncio.wait_for(node_checker.node_health_check(), timeout=2)
        await asyncio.wait_for(node_checker.node_health_check(), timeout=2)
        # The slow node keeps its single check; the others are checked on every run.
        assert checked == {1: 1, 2: 2, 3: 2}
    finally:
        release.set()
        for _ in range(10):
            await asyncio.sleep(0)
    await asyncio.wait_for(node_checker.node_health_check(), timeout=2)
    assert checked == {1: 2, 2: 3, 3: 3}


@pytest.mark.asyncio
async def test_a_check_that_raises_is_logged_and_runs_again(monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr(node_checker, "logger", logger)
    checked = collections.Counter()

    async def check(db_node, node):
        checked[db_node.id] += 1
        if db_node.id == 1:
            raise RuntimeError("boom")

    _health_run(monkeypatch, check, count=2)
    await asyncio.wait_for(node_checker.node_health_check(), timeout=2)
    await asyncio.wait_for(node_checker.node_health_check(), timeout=2)

    assert checked == {1: 2, 2: 2}
    assert node_checker._check_tasks == {}
    assert [call.args[1] for call in logger.error.call_args_list] == ["node-1", "node-1"]


@pytest.mark.asyncio
async def test_shutdown_cancels_checks_still_running(monkeypatch):
    cancelled = []

    async def check(db_node, node):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append(db_node.id)
            raise

    _health_run(monkeypatch, check, count=2)
    await asyncio.wait_for(node_checker.node_health_check(), timeout=2)
    assert node_checker._check_tasks.keys() == {1, 2}

    await asyncio.wait_for(node_checker._stop_node_loops(), timeout=2)

    assert sorted(cancelled) == [1, 2]
    assert node_checker._check_tasks == {}
