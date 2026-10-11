"""Large WireGuard starts: an empty Start, then the snapshot in bounded batches."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PasarGuardNodeBridge import NodeAPIError
from PasarGuardNodeBridge.common import service_pb2 as service

from app.db.models import Node
from app.models.core import CoreType
from app.node import NodeManager
from app.operation import node as node_operation_module
from app.operation.node import (
    WIREGUARD_BATCHED_START_THRESHOLD,
    WIREGUARD_START_BATCH_SIZE,
    NodeOperation,
)

NODE_ID = 7
STARTED = SimpleNamespace(node_version="0.5.4", core_version="1.0.0")


class _FakeNode:
    """Records Start, the delta batches and Stop in call order."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.name = kwargs.get("name")
        self.calls: list[tuple] = []
        self.on_start = None
        self.on_batch = None

    async def get_extra(self):
        return self.kwargs.get("extra", {})

    async def set_health(self, health):
        pass

    async def get_lifecycle_state(self):
        return None

    async def start(self, **kwargs):
        self.calls.append(("start", len(kwargs["users"])))
        if self.on_start is not None:
            await self.on_start()
        return STARTED

    async def stop(self, timeout=None):
        self.calls.append(("stop",))

    async def _supports_chunked_sync(self):
        return True, "0.5.4"

    async def sync_users_chunked(self, batch, chunk_size, flush_pending):
        self.calls.append(("batch", len(batch), chunk_size, flush_pending))
        if self.on_batch is not None:
            await self.on_batch(len([call for call in self.calls if call[0] == "batch"]))
        return []


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> NodeManager:
    manager = NodeManager()
    monkeypatch.setattr(node_operation_module, "node_manager", manager)
    return manager


def _core(core_type: CoreType):
    return SimpleNamespace(type=core_type, to_str=lambda: "{}", exclude_inbound_tags=[])


def _backend(core_type: CoreType):
    return service.BackendType.WIREGUARD if core_type == CoreType.wg else service.BackendType.XRAY


async def _start(pg_node: _FakeNode, users: list, core_type: CoreType = CoreType.wg):
    db_node = SimpleNamespace(id=NODE_ID, name="wg-node", keep_alive=60)
    return await NodeOperation._start_or_attach_node(pg_node, db_node, _core(core_type), users, _backend(core_type))


def _batches(pg_node: _FakeNode) -> list[int]:
    return [call[1] for call in pg_node.calls if call[0] == "batch"]


@pytest.mark.asyncio
async def test_large_wireguard_start_sends_empty_start_then_batches(manager: NodeManager):
    pg_node = _FakeNode()
    manager._nodes[NODE_ID] = pg_node
    users = [object() for _ in range(WIREGUARD_BATCHED_START_THRESHOLD + 50)]

    assert await _start(pg_node, users) is STARTED

    size = WIREGUARD_START_BATCH_SIZE
    full_batches, rest = divmod(len(users), size)
    assert rest
    expected = [("start", 0)] + [("batch", size, size, False)] * full_batches + [("batch", rest, rest, False)]
    assert pg_node.calls == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("core_type", "user_count", "batched"),
    [
        (CoreType.wg, WIREGUARD_BATCHED_START_THRESHOLD - 1, False),
        (CoreType.wg, WIREGUARD_BATCHED_START_THRESHOLD, True),
        (CoreType.xray, WIREGUARD_BATCHED_START_THRESHOLD + 50, False),
    ],
)
async def test_batched_start_threshold(manager: NodeManager, core_type: CoreType, user_count: int, batched: bool):
    pg_node = _FakeNode()
    manager._nodes[NODE_ID] = pg_node

    await _start(pg_node, [object() for _ in range(user_count)], core_type)

    if batched:
        assert pg_node.calls[0] == ("start", 0)
        assert sum(_batches(pg_node)) == user_count
    else:
        assert pg_node.calls == [("start", user_count)]


@pytest.mark.asyncio
async def test_failed_batch_stops_the_current_node(manager: NodeManager):
    pg_node = _FakeNode()
    manager._nodes[NODE_ID] = pg_node

    async def fail_third(batch_number: int):
        if batch_number == 3:
            raise NodeAPIError(-1, "Request timed out")

    pg_node.on_batch = fail_third

    with pytest.raises(NodeAPIError) as exc_info:
        await _start(pg_node, [object() for _ in range(WIREGUARD_BATCHED_START_THRESHOLD)])

    assert exc_info.value.code == 500
    assert _batches(pg_node) == [WIREGUARD_START_BATCH_SIZE] * 3
    # The half-populated backend is stopped so the next connect starts it cleanly.
    assert pg_node.calls[-1] == ("stop",)


@pytest.mark.asyncio
async def test_failed_start_does_not_stop_a_replaced_node(manager: NodeManager):
    """An edit can swap the node object between Start and the batches; the old object's
    failure must not stop the backend the replacement now owns."""
    pg_node = _FakeNode()
    replacement = _FakeNode()
    manager._nodes[NODE_ID] = pg_node

    async def replace():
        manager._nodes[NODE_ID] = replacement

    pg_node.on_start = replace

    with pytest.raises(NodeAPIError) as exc_info:
        await _start(pg_node, [object() for _ in range(WIREGUARD_BATCHED_START_THRESHOLD)])

    assert exc_info.value.code == 500
    assert pg_node.calls == [("start", 0)]
    assert replacement.calls == []


@pytest.mark.asyncio
async def test_cancelled_batched_start_stops_the_current_node(manager: NodeManager):
    pg_node = _FakeNode()
    manager._nodes[NODE_ID] = pg_node
    entered = asyncio.Event()

    async def hang(batch_number: int):
        if batch_number == 2:
            entered.set()
            await asyncio.Event().wait()

    pg_node.on_batch = hang

    start = asyncio.create_task(_start(pg_node, [object() for _ in range(WIREGUARD_BATCHED_START_THRESHOLD)]))
    await asyncio.wait_for(entered.wait(), 1)
    start.cancel()

    with pytest.raises(asyncio.CancelledError):
        await start

    assert _batches(pg_node) == [WIREGUARD_START_BATCH_SIZE] * 2
    assert pg_node.calls[-1] == ("stop",)


def _db_node(**overrides) -> Node:
    fields = {
        "name": "wg-node",
        "address": "10.0.0.1",
        "port": 1000,
        "api_port": 1001,
        "server_ca": "ca",
        "api_key": "key",
        "core_config_id": None,
        "usage_coefficient": 1.0,
    }
    fields.update(overrides)
    node = Node(**fields)
    node.id = NODE_ID
    return node


@pytest.fixture
def managed(manager: NodeManager, monkeypatch: pytest.MonkeyPatch) -> NodeManager:
    """A manager whose update_node creates fake bridge objects."""
    monkeypatch.setattr("app.node.ensure_bridge_memory", AsyncMock(return_value=None))
    monkeypatch.setattr("app.node.get_bridge_memory", lambda: (None, None, None))
    monkeypatch.setattr("app.node.create_node", lambda **kwargs: _FakeNode(**kwargs))
    return manager


def _hold_second_batch(pg_node: _FakeNode) -> tuple[asyncio.Event, asyncio.Event]:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold(batch_number: int):
        if batch_number == 2:
            entered.set()
            await release.wait()

    pg_node.on_batch = hold
    return entered, release


async def _settle():
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["connection_change", "removal"])
async def test_lifecycle_change_preempts_batched_start(managed: NodeManager, lifecycle: str):
    pg_node = await managed.update_node(_db_node())
    entered, _release = _hold_second_batch(pg_node)
    start = asyncio.create_task(_start(pg_node, [object() for _ in range(WIREGUARD_BATCHED_START_THRESHOLD)]))
    await asyncio.wait_for(entered.wait(), 1)

    replacement = None
    if lifecycle == "connection_change":
        replacement = await asyncio.wait_for(managed.update_node(_db_node(address="10.0.0.2")), 1)
    else:
        await asyncio.wait_for(managed.remove_node(NODE_ID), 1)

    with pytest.raises(NodeAPIError) as exc_info:
        await asyncio.wait_for(start, 1)
    # -4 makes connect_node skip: the preempting operation owns the node now.
    assert exc_info.value.code == -4
    assert _batches(pg_node) == [WIREGUARD_START_BATCH_SIZE] * 2
    await _settle()  # removal stops the old backend in a background task
    # The lifecycle operation stopped the old backend once; the preempted start did not.
    assert pg_node.calls.count(("stop",)) == 1
    if replacement is not None:
        assert replacement.calls == []
    assert managed._user_sync_tasks == {}


@pytest.mark.asyncio
async def test_metadata_edit_waits_for_batched_start(managed: NodeManager):
    pg_node = await managed.update_node(_db_node())
    entered, release = _hold_second_batch(pg_node)
    users = [object() for _ in range(WIREGUARD_BATCHED_START_THRESHOLD)]
    start = asyncio.create_task(_start(pg_node, users))
    await asyncio.wait_for(entered.wait(), 1)

    edit = asyncio.create_task(managed.update_node(_db_node(name="renamed")))
    await _settle()
    assert not edit.done()

    release.set()
    assert await asyncio.wait_for(start, 1) is STARTED
    replacement = await asyncio.wait_for(edit, 1)

    assert replacement is not pg_node
    assert sum(_batches(pg_node)) == len(users)
    # A metadata-only edit swaps the bridge object without a remote Stop.
    assert ("stop",) not in pg_node.calls
