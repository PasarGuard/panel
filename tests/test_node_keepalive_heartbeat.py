"""Per-node keep-alive heartbeat, independent of the batch jobs."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import certifi
import pytest
from grpclib.client import Channel
from grpclib.const import Cardinality, Handler
from grpclib.server import Server
from PasarGuardNodeBridge import Health, NodeType
from PasarGuardNodeBridge.common import service_grpc, service_pb2 as service
from sqlalchemy.exc import IntegrityError

from app.db.models import Node, NodeConnectionType, NodeStatus
from app.jobs import node_heartbeat as heartbeat_job
from app.models.node import NodeCreate, NodeModify
from app.nats import leader as leader_module
from app.node import NodeManager, heartbeat as heartbeat_module
from app.node.bridge import create_node
from app.node.heartbeat import NodeHeartbeat, heartbeat_interval, keep_alive_too_short, shortest_safe_keep_alive
from app.operation import OperatorType, node as node_operation
from app.operation.node import NodeOperation


class _FakeBridgeNode:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.name = kwargs.get("name")
        self.health = Health.HEALTHY
        self.beats: list[float] = []
        self.hang: asyncio.Event | None = None
        self.down = False
        self.cancelled = False

    async def get_extra(self):
        return self.kwargs.get("extra", {})

    async def get_health(self):
        return self.health

    async def set_health(self, health):
        self.health = health

    async def stop(self, timeout=None):
        pass

    async def info(self, timeout=None):
        self.beats.append(timeout)
        if self.hang is not None:
            try:
                await self.hang.wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        if self.down:
            raise TimeoutError
        return SimpleNamespace(started=True)


async def _ready():
    return None


def _db_node(node_id: int, keep_alive: int, **overrides) -> Node:
    fields = {
        "name": f"n{node_id}",
        "address": "10.0.0.1",
        "port": 1000,
        "api_port": 1001,
        "server_ca": "ca",
        "api_key": "key",
        "core_config_id": None,
        "keep_alive": keep_alive,
    }
    fields.update(overrides)
    node = Node(**fields)
    node.id = node_id
    return node


@pytest.fixture
def beat(monkeypatch):
    monkeypatch.setattr("app.node.ensure_bridge_memory", _ready)
    monkeypatch.setattr("app.node.get_bridge_memory", lambda: (None, None, None))
    monkeypatch.setattr("app.node.create_node", lambda **kwargs: _FakeBridgeNode(**kwargs))
    monkeypatch.setattr(heartbeat_module, "needs_job_leader", lambda: False)
    clock = [500.0]
    monkeypatch.setattr(heartbeat_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    manager = NodeManager()
    heartbeat = NodeHeartbeat(manager)

    async def tick_at(*offsets):
        start = clock[0]
        for offset in offsets:
            clock[0] = start + offset
            await heartbeat.tick()
            for _ in range(3):
                await asyncio.sleep(0)
        clock[0] = start + offsets[-1]

    yield SimpleNamespace(manager=manager, heartbeat=heartbeat, tick_at=tick_at, clock=clock, monkeypatch=monkeypatch)


def test_interval_follows_keep_alive_within_bounds():
    assert [heartbeat_interval(value) for value in (8, 20, 40, 60, 600)] == [5, 5, 10, 15, 15]


def _workers(monkeypatch, count: int):
    # Several workers elect a job leader over NATS.
    monkeypatch.setattr(leader_module, "is_nats_enabled", lambda: count > 1)
    monkeypatch.setattr(leader_module.server_settings, "workers", count)


def test_keep_alive_must_survive_two_lost_beats(monkeypatch):
    _workers(monkeypatch, 1)
    assert [keep_alive_too_short(value) for value in (0, 5, 19, 20, 30, 60, 600)] == [
        False,
        True,
        True,
        False,
        False,
        False,
        False,
    ]
    assert shortest_safe_keep_alive() == 20


def test_keep_alive_must_also_survive_a_job_leader_change(monkeypatch):
    # With several workers only the leader beats; a new one takes over up to 20 s after it dies.
    _workers(monkeypatch, 4)
    assert [keep_alive_too_short(value) for value in (0, 19, 20, 30, 39, 40, 60, 600)] == [
        False,
        True,
        True,
        True,
        True,
        False,
        False,
        False,
    ]
    assert shortest_safe_keep_alive() == 40


@pytest.mark.asyncio
async def test_each_node_is_beaten_at_its_own_interval(beat):
    slow = await beat.manager.update_node(_db_node(1, keep_alive=60))
    fast = await beat.manager.update_node(_db_node(2, keep_alive=20))
    off = await beat.manager.update_node(_db_node(3, keep_alive=0))
    try:
        await beat.tick_at(0, 5, 10, 15)

        assert slow.beats == [15, 15]
        assert fast.beats == [5, 5, 5, 5]
        assert off.beats == []
    finally:
        await beat.heartbeat.stop()


@pytest.mark.asyncio
async def test_a_slow_node_never_has_two_beats_in_flight(beat):
    node = await beat.manager.update_node(_db_node(1, keep_alive=60))
    node.hang = asyncio.Event()
    try:
        await beat.tick_at(0, 15, 30, 45)
        assert len(node.beats) == 1

        node.hang.set()
        for _ in range(3):
            await asyncio.sleep(0)
        await beat.tick_at(0)
        assert len(node.beats) == 2
    finally:
        await beat.heartbeat.stop()


@pytest.mark.asyncio
async def test_removed_node_stops_beating(beat):
    node = await beat.manager.update_node(_db_node(1, keep_alive=60))
    node.hang = asyncio.Event()
    try:
        await beat.tick_at(0)

        await beat.manager.remove_node(1, remote_stop=False)
        await beat.tick_at(0, 30, 60)

        assert node.cancelled
        assert len(node.beats) == 1
    finally:
        await beat.heartbeat.stop()


@pytest.mark.asyncio
async def test_keep_alive_edits_change_the_cadence(beat):
    node = await beat.manager.update_node(_db_node(1, keep_alive=60))
    try:
        await beat.tick_at(0)
        assert await beat.manager.update_node(_db_node(1, keep_alive=20)) is node
        await beat.tick_at(10, 15, 20, 25)
        assert node.beats == [15, 5, 5, 5]

        await beat.manager.update_node(_db_node(1, keep_alive=0))
        await beat.tick_at(30, 60)
        assert len(node.beats) == 4
    finally:
        await beat.heartbeat.stop()


@pytest.mark.asyncio
async def test_only_the_job_leader_beats(beat):
    node = await beat.manager.update_node(_db_node(1, keep_alive=60))
    leader = [False]
    beat.monkeypatch.setattr(heartbeat_module, "needs_job_leader", lambda: True)
    beat.monkeypatch.setattr(heartbeat_module, "is_job_leader", lambda: leader[0])
    try:
        await beat.tick_at(0, 15)
        assert node.beats == []

        leader[0] = True
        await beat.tick_at(0)
        assert node.beats == [15]
    finally:
        await beat.heartbeat.stop()


@pytest.mark.asyncio
async def test_nodes_being_torn_down_are_skipped(beat):
    node = await beat.manager.update_node(_db_node(1, keep_alive=60))
    node.health = Health.INVALID
    try:
        await beat.tick_at(0, 15)
        assert node.beats == []
    finally:
        await beat.heartbeat.stop()


@pytest.mark.asyncio
async def test_answers_are_kept_per_bridge_object(beat):
    node = await beat.manager.update_node(_db_node(1, keep_alive=60))
    try:
        await beat.tick_at(0)
        answered = beat.clock[0]
        assert beat.heartbeat.answered_since(1, node, answered - 1)
        assert not beat.heartbeat.answered_since(1, node, answered)
        # An answer to an older connection object says nothing about the new one.
        assert not beat.heartbeat.answered_since(1, _FakeBridgeNode(), answered - 1)

        # A lost beat records nothing.
        node.down = True
        await beat.tick_at(15)
        assert not beat.heartbeat.answered_since(1, node, answered)

        await beat.manager.remove_node(1, remote_stop=False)
        await beat.tick_at(0)
        assert not beat.heartbeat.answered_since(1, node, 0)
    finally:
        await beat.heartbeat.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("runs_node", [True, False])
async def test_heartbeat_starts_only_where_the_node_connections_live(monkeypatch, runs_node):
    start, shutdown_hooks = MagicMock(), []
    monkeypatch.setattr(heartbeat_job.node_heartbeat, "start", start)
    monkeypatch.setattr(heartbeat_job, "on_shutdown", shutdown_hooks.append)
    monkeypatch.setattr(heartbeat_job, "runtime_settings", SimpleNamespace(role=SimpleNamespace(runs_node=runs_node)))

    await heartbeat_job.start_node_heartbeat()

    assert start.called is runs_node
    assert shutdown_hooks == ([heartbeat_job.node_heartbeat.stop] if runs_node else [])


@pytest.mark.asyncio
async def test_heartbeat_sends_get_base_info_over_grpc(monkeypatch):
    # CI's multi-worker jobs would otherwise make this process a non-leader that never beats.
    monkeypatch.setattr(heartbeat_module, "needs_job_leader", lambda: False)
    received = []

    async def get_base_info(stream):
        await stream.recv_message()
        received.append(stream.metadata.get("x-api-key"))
        await stream.send_message(service.BaseInfoResponse(started=True, core_version="26.10.21", node_version="0.5.4"))

    class Receiver:
        def __mapping__(self):
            return {
                "/service.NodeService/GetBaseInfo": Handler(
                    get_base_info, Cardinality.UNARY_UNARY, service.Empty, service.BaseInfoResponse
                )
            }

    server = Server([Receiver()])
    await server.start("127.0.0.1", 0)
    port = server._server.sockets[0].getsockname()[1]
    api_key = str(uuid4())
    node = create_node(
        connection=NodeType.grpc,
        address="127.0.0.1",
        port=port,
        api_port=1,
        server_ca=certifi.contents(),
        api_key=api_key,
        name="real-grpc",
        node_id=f"heartbeat-{uuid4()}",
    )
    node.channel.close()
    node.channel = Channel("127.0.0.1", port, ssl=False)
    node._client = service_grpc.NodeServiceStub(node.channel)
    heartbeat = NodeHeartbeat(SimpleNamespace(get_keep_alive_nodes=AsyncMock(return_value=[(1, node, 60)])))
    try:
        await heartbeat.tick()
        async with asyncio.timeout(5):
            while not received:
                await asyncio.sleep(0.01)
        assert received == [api_key]
    finally:
        await heartbeat.stop()
        node.channel.close()
        server.close()
        await server.wait_closed()


def _node_fields(**overrides) -> dict:
    fields = {
        "name": "short-keep-alive",
        "address": "node.example.com",
        "port": 62050,
        "api_port": 62051,
        "usage_coefficient": 1.0,
        "connection_type": NodeConnectionType.grpc,
        "server_ca": "ca",
        "keep_alive": 60,
        "core_config_id": 1,
        "api_key": str(uuid4()),
    }
    fields.update(overrides)
    return fields


def _stored_node(**overrides):
    return SimpleNamespace(
        **(
            _node_fields()
            | {
                "id": 5,
                "sort_order": 0,
                "data_limit": 0,
                "data_limit_reset_strategy": "no_reset",
                "reset_time": -1,
                "default_timeout": 10,
                "internal_timeout": 15,
                "proxy_url": None,
                "xray_version": None,
                "node_version": None,
                "status": NodeStatus.connecting,
                "message": None,
                "uplink": 0,
                "downlink": 0,
                "lifetime_uplink": 0,
                "lifetime_downlink": 0,
            }
            | overrides
        )
    )


@pytest.fixture
def operation(monkeypatch):
    operator = NodeOperation(OperatorType.SYSTEM)
    operator.get_validated_core_config = AsyncMock()
    operator._update_node_impl = AsyncMock()
    operator._connect_single_node_background = AsyncMock()
    logger = MagicMock()
    monkeypatch.setattr(node_operation, "logger", logger)
    _workers(monkeypatch, 1)
    monkeypatch.setattr(node_operation.notification, "create_node", AsyncMock())
    monkeypatch.setattr(node_operation.notification, "modify_node", AsyncMock())
    return SimpleNamespace(operator=operator, logger=logger, monkeypatch=monkeypatch)


def _warnings(logger) -> list[str]:
    return [call.args[0] % call.args[1:] for call in logger.warning.call_args_list]


@pytest.mark.asyncio
@pytest.mark.parametrize("keep_alive, warned", [(10, True), (0, False), (20, False), (60, False)])
async def test_create_warns_about_a_keep_alive_the_heartbeat_cannot_hold(operation, keep_alive, warned):
    stored = _stored_node(keep_alive=keep_alive)
    operation.monkeypatch.setattr(node_operation, "create_node", AsyncMock(return_value=stored))

    new_node = NodeCreate.model_construct(**_node_fields(keep_alive=keep_alive))
    await operation.operator.create_node(object(), new_node, MagicMock())

    warnings = _warnings(operation.logger)
    assert bool(warnings) is warned
    if warned:
        assert "keep_alive" in warnings[0] and "short-keep-alive" in warnings[0]


@pytest.mark.asyncio
async def test_create_warns_with_the_minimum_for_several_workers(operation):
    _workers(operation.monkeypatch, 4)
    operation.monkeypatch.setattr(node_operation, "create_node", AsyncMock(return_value=_stored_node(keep_alive=30)))

    await operation.operator.create_node(
        object(), NodeCreate.model_construct(**_node_fields(keep_alive=30)), MagicMock()
    )

    (warning,) = _warnings(operation.logger)
    assert "job leader change" in warning and "at least 40s" in warning


@pytest.mark.asyncio
async def test_rejected_create_does_not_warn(operation):
    duplicate = IntegrityError("INSERT", {}, Exception("duplicate"))
    operation.monkeypatch.setattr(node_operation, "create_node", AsyncMock(side_effect=duplicate))

    with pytest.raises(ValueError):
        await operation.operator.create_node(
            SimpleNamespace(rollback=AsyncMock()),
            NodeCreate.model_construct(**_node_fields(keep_alive=10)),
            MagicMock(),
        )

    assert _warnings(operation.logger) == []


@pytest.mark.asyncio
async def test_modify_warns_only_when_keep_alive_changes_to_a_short_value(operation):
    stored = _stored_node(keep_alive=60, status=NodeStatus.connected)
    operation.operator.get_validated_node = AsyncMock(return_value=stored)

    async def modify(db, db_node, modified):
        for field, value in modified.model_dump(exclude_none=True).items():
            setattr(db_node, field, value)
        return db_node

    operation.monkeypatch.setattr(node_operation, "modify_node", modify)

    await operation.operator.modify_node(object(), 5, NodeModify(keep_alive=10), MagicMock())
    assert len(_warnings(operation.logger)) == 1

    # Saving the form again (bulk enable/disable sends every field) does not repeat it.
    await operation.operator.modify_node(object(), 5, NodeModify(keep_alive=10, name="renamed"), MagicMock())
    assert len(_warnings(operation.logger)) == 1
