"""Independent delivery worker for the real NATS + gRPC full-sync tests.

Runs one QueuedGrpcNode against a shared JetStream bucket and a local gRPC
receiver, delivering whatever is queued for the node, then exits (or dies on
command) so the parent can observe cross-process fencing and recovery.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import certifi
import nats
from grpclib.client import Channel
from PasarGuardNodeBridge.common import service_grpc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PasarGuardNodeBridge.common.service_pb2 import User

from app.node.bridge import QueuedGrpcNode, register_refresh_handler
from app.node.nats_memory import NatsUserSyncStore


async def main():
    url, bucket, node_id, port, worker_id, mode, seconds = sys.argv[1:]
    nc = await nats.connect(url)
    kv = await nc.jetstream().key_value(bucket)
    store = NatsUserSyncStore(kv)
    register_refresh_handler(lambda _node, emails: current_state(kv, node_id, emails))
    node = QueuedGrpcNode(
        address="127.0.0.1",
        port=int(port),
        api_port=1,
        server_ca=certifi.contents(),
        api_key=str(uuid4()),
        node_id=node_id,
        user_sync_store=store,
        worker_id=worker_id,
        sync_lease_seconds=3.0,
    )
    node.channel.close()
    node.channel = Channel("127.0.0.1", int(port), ssl=False)
    node._client = service_grpc.NodeServiceStub(node.channel)
    node._sync_poll_interval = 0.05
    node._worker_idle_timeout = 0.5
    try:
        await node.connect("0.5.4", "26.3.27")
        print("READY", flush=True)
        if mode == "die-after-send":
            # The parent tells us (via stdin) when our delivery has landed; exit
            # without acknowledging, as a crashed worker would.
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, sys.stdin.readline)
            os._exit(1)
        await asyncio.sleep(float(seconds))
        print(json.dumps({"worker": worker_id, "progress": node._worker_progress}), flush=True)
    finally:
        await node.disconnect()
        node.channel.close()
        await node._json_client.close()
        await store.close()
        await nc.close()


async def current_state(kv, node_id, emails):
    """The test's source of truth: a JSON map kept in the same bucket by the parent."""
    entry = await kv.get(f"testdb.{node_id}.state")
    database = json.loads(entry.value)
    return [User(email=email, inbounds=database.get(email, [])) for email in emails]


if __name__ == "__main__":
    asyncio.run(main())
