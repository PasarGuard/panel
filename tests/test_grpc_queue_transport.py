"""Bounded queue delivery over a real gRPC receiver with real JetStream, including an RPC failure and retry."""

import asyncio
from uuid import uuid4

import certifi
from grpclib.client import Channel
from grpclib.const import Cardinality, Handler, Status
from grpclib.exceptions import GRPCError
from grpclib.server import Server
from PasarGuardNodeBridge.common import service_grpc, service_pb2 as service

from app.node.bridge import QueuedGrpcNode
from app.node.nats_memory import NatsUserSyncStore
from app.operation import node as node_operation
from config import nats_settings
from tests.test_nats_sync_integration import jetstream, wait_for_keys  # noqa: F401


async def test_real_grpc_and_nats_deliver_bounded_queue_after_rpc_failure(jetstream, monkeypatch):  # noqa: F811
    class Receiver:
        def __init__(self):
            self.calls = 0
            self.delivered = []

        async def receive(self, stream):
            users = []
            async for chunk in stream:
                users.extend(chunk.users)
                if chunk.last:
                    break
            assert 1 <= len(users) <= 100
            self.calls += 1
            if self.calls == 1:
                raise GRPCError(Status.UNAVAILABLE, "temporary receiver failure")
            self.delivered.extend(user.email for user in users)
            await stream.send_message(service.Empty())

        def __mapping__(self):
            return {
                "/service.NodeService/SyncUsersChunked": Handler(
                    self.receive, Cardinality.STREAM_UNARY, service.UsersChunk, service.Empty
                )
            }

    receiver = Receiver()
    server = Server([receiver])
    await server.start("127.0.0.1", 0)
    port = server._server.sockets[0].getsockname()[1]
    store = NatsUserSyncStore(jetstream.kv)
    node = QueuedGrpcNode(
        address="127.0.0.1",
        port=port,
        api_port=1,
        server_ca=certifi.contents(),
        api_key=str(uuid4()),
        node_id="transport",
        user_sync_store=store,
    )
    node.channel.close()
    node.channel = Channel("127.0.0.1", port, ssl=False)
    node._client = service_grpc.NodeServiceStub(node.channel)
    monkeypatch.setattr(node_operation, "needs_shared_bridge_memory", lambda: True)
    monkeypatch.setattr(nats_settings, "node_update_users_batch_size", 100)
    try:
        await store.enqueue_users("transport", [service.User(email=f"queued-{i}") for i in range(1200)])
        await node.connect("0.5.4", "26.3.27")
        await node_operation.NodeOperation._resume_shared_sync(node)
        async with asyncio.timeout(20):
            while len(receiver.delivered) < 1200:
                await asyncio.sleep(0.02)
            await wait_for_keys(store, "p.transport.", 0)
        assert receiver.calls == 13
        assert len(set(receiver.delivered)) == 1200
    finally:
        await node.disconnect()
        node.channel.close()
        await store.close()
        server.close()
        await server.wait_closed()
