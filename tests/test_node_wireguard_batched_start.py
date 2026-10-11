"""Large WireGuard starts: an empty Start, then the snapshot in bounded batches."""

import asyncio
from types import SimpleNamespace

import pytest
from PasarGuardNodeBridge import NodeAPIError
from PasarGuardNodeBridge.common import service_pb2 as service

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

    def __init__(self):
        self.calls: list[tuple] = []
        self.on_start = None
        self.on_batch = None

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
