"""Isolated worker for reconnect fan-out tests against a real NATS server."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import nats
from PasarGuardNodeBridge import Health

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import NodeStatus
from app.node import manager_sync
from app.operation import node as node_operation


class MetadataSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


async def main():
    url, subject, worker_id, expected = sys.argv[1:]
    node = SimpleNamespace(get_health=AsyncMock(return_value=Health.HEALTHY), start=AsyncMock())
    core = SimpleNamespace(inbounds=["in"], protocols=frozenset())
    manager_sync.WORKER_ID = worker_id
    manager_sync.GetDB = MetadataSession
    manager_sync.get_node_by_id = AsyncMock(
        return_value=SimpleNamespace(id=91, status=NodeStatus.connected, core_config_id=1)
    )
    node_operation.node_manager.update_node = AsyncMock(return_value=node)
    node_operation.node_manager.get_node = AsyncMock(return_value=node)
    node_operation.core_manager.get_cores = AsyncMock(return_value={1: core})
    reads = AsyncMock(return_value=[])
    node_operation.core_users = reads
    done = asyncio.Event()
    count = 0

    async def received(message):
        nonlocal count
        await manager_sync.handle_node_message(json.loads(message.data))
        count += 1
        if count == int(expected):
            done.set()

    nc = await nats.connect(url)
    try:
        await nc.subscribe(subject, cb=received)
        await nc.flush()
        print("READY", flush=True)
        async with asyncio.timeout(30):
            await done.wait()
        print(
            json.dumps({"handled": count, "user_reads": reads.await_count, "starts": node.start.await_count}),
            flush=True,
        )
    finally:
        await nc.close()


if __name__ == "__main__":
    asyncio.run(main())
