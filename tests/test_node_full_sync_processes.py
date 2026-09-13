"""Full-sync fencing and crash recovery with real JetStream, a real gRPC receiver, and independent worker processes."""

import asyncio
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import certifi
import pytest
from grpclib.client import Channel
from grpclib.const import Cardinality, Handler
from grpclib.server import Server
from PasarGuardNodeBridge.common import service_grpc, service_pb2 as service

from app.node import NodeManager
from app.node.bridge import QueuedGrpcNode, register_refresh_handler
from app.node.nats_memory import NatsUserSyncStore
from tests.test_nats_sync_integration import jetstream  # noqa: F401 - real NATS fixture

WORKER = Path(__file__).with_name("node_delivery_process_worker.py")


class Receiver:
    """A node stand-in: full SyncUsers replaces the user set, chunked deltas merge into it."""

    def __init__(self):
        self.users: dict[str, list[str]] = {}
        self.events: list[tuple[str, list[str]]] = []
        self.delta_landed = asyncio.Event()
        self.delay_prefix = "slow-"
        self.delay_seconds = 1.0

    def __mapping__(self):
        return {
            "/service.NodeService/SyncUsers": Handler(self.full, Cardinality.UNARY_UNARY, service.Users, service.Empty),
            "/service.NodeService/SyncUsersChunked": Handler(
                self.chunked, Cardinality.STREAM_UNARY, service.UsersChunk, service.Empty
            ),
        }

    async def full(self, stream):
        request = await stream.recv_message()
        self.users = {user.email: list(user.inbounds) for user in request.users}
        self.events.append(("full", sorted(self.users)))
        await stream.send_message(service.Empty())

    async def chunked(self, stream):
        users = []
        async for chunk in stream:
            users.extend(chunk.users)
            if chunk.last:
                break
        if any(user.email.startswith(self.delay_prefix) for user in users):
            await asyncio.sleep(self.delay_seconds)
        for user in users:
            self.users[user.email] = list(user.inbounds)
        self.events.append(("delta", [f"{user.email}={list(user.inbounds)}" for user in users]))
        self.delta_landed.set()
        await stream.send_message(service.Empty())


@contextlib.asynccontextmanager
async def receiver_server():
    receiver = Receiver()
    server = Server([receiver])
    await server.start("127.0.0.1", 0)
    try:
        yield receiver, server._server.sockets[0].getsockname()[1]
    finally:
        server.close()
        await server.wait_closed()


def make_local_node(store, node_id, port, worker_id):
    node = QueuedGrpcNode(
        address="127.0.0.1",
        port=port,
        api_port=1,
        server_ca=certifi.contents(),
        api_key=str(uuid4()),
        node_id=node_id,
        user_sync_store=store,
        worker_id=worker_id,
        sync_lease_seconds=3.0,
    )
    node.channel.close()
    node.channel = Channel("127.0.0.1", port, ssl=False)
    node._client = service_grpc.NodeServiceStub(node.channel)
    node._sync_poll_interval = 0.05
    node._worker_idle_timeout = 0.5
    return node


async def start_worker(js, node_id, port, worker_id, mode="run", seconds="12"):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(WORKER),
        js.url,
        js.bucket,
        node_id,
        str(port),
        worker_id,
        mode,
        seconds,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    async with asyncio.timeout(30):
        assert (await process.stdout.readline()).strip() == b"READY"
    return process


async def finish_worker(process):
    if process.returncode is None:
        process.kill()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(process.wait(), 10)


async def wait_until(predicate, timeout=20):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.02)


class Database:
    """Source of truth shared with the worker process through the bucket."""

    def __init__(self, kv, node_id):
        self.kv, self.key, self.state = kv, f"testdb.{node_id}.state", {}

    async def set(self, email, inbounds):
        self.state[email] = inbounds
        await self.kv.put(self.key, json.dumps(self.state).encode())

    def snapshot(self):
        return [service.User(email=email, inbounds=inbounds) for email, inbounds in self.state.items()]

    async def resolve(self, _node, emails):
        return [service.User(email=email, inbounds=self.state.get(email, [])) for email in emails]


@pytest.mark.asyncio
@pytest.mark.parametrize("flush", [False, True])
async def test_delivery_from_another_process_crossing_a_snapshot_converges_to_latest_state(jetstream, flush):  # noqa: F811
    node_id = "fence-" + uuid4().hex[:6]
    async with receiver_server() as (receiver, port):
        writer = NatsUserSyncStore(jetstream.kv)
        local = NatsUserSyncStore(jetstream.kv)
        database = Database(jetstream.kv, node_id)
        node = make_local_node(local, node_id, port, "parent")
        manager = NodeManager()
        manager._nodes[1] = node
        register_refresh_handler(database.resolve)
        worker = await start_worker(jetstream, node_id, port, "worker-a")
        try:
            # v1 is committed and queued; the other process claims it and its RPC is slow.
            await database.set("slow-user", ["v1"])
            await database.set("other-user", ["stable"])
            await writer.enqueue_users(node_id, [service.User(email="slow-user", inbounds=["v1"])])
            await asyncio.sleep(0.4)
            captured, active = await local.capture_queued(node_id)
            assert active == 1 and captured == {}

            async def snapshot_then_concurrent_change():
                snapshot = database.snapshot()  # read after quiescence: contains v1
                # An API edit commits and enqueues while the snapshot is being applied.
                await database.set("slow-user", ["v2"])
                await writer.enqueue_users(node_id, [service.User(email="slow-user", inbounds=["v2"])])
                return snapshot

            await node.connect("0.5.4", "26.3.27")
            await manager.sync_full(1, snapshot_then_concurrent_change, flush_pending=flush)
            # Quiescence held the snapshot RPC until the in-flight v1 delivery had landed.
            assert [kind for kind, _ in receiver.events[:2]] == ["delta", "full"]
            assert receiver.events[1] == ("full", ["other-user", "slow-user"])
            # The change made after the snapshot read was fenced, not lost, and lands after it.
            await wait_until(lambda: receiver.users.get("slow-user") == ["v2"])
            async with asyncio.timeout(20):
                while (await local.capture_queued(node_id)) != ({}, 0):
                    await asyncio.sleep(0.05)
            assert receiver.users == database.state
            # Nothing older than the snapshot was replayed after it.
            assert all(entries != ["slow-user=['v1']"] for kind, entries in receiver.events[2:] if kind == "delta")
        finally:
            register_refresh_handler(None)
            await finish_worker(worker)
            await node.disconnect()
            node.channel.close()
            await node._json_client.close()
            await local.close()
            await writer.close()


@pytest.mark.asyncio
async def test_worker_process_that_dies_after_sending_and_before_acking_is_recovered(jetstream):  # noqa: F811
    node_id = "crash-" + uuid4().hex[:6]
    async with receiver_server() as (receiver, port):
        receiver.delay_seconds = 0.3
        writer = NatsUserSyncStore(jetstream.kv)
        local = NatsUserSyncStore(jetstream.kv)
        node = make_local_node(local, node_id, port, "parent")
        manager = NodeManager()
        manager._nodes[1] = node
        worker = await start_worker(jetstream, node_id, port, "worker-a", mode="die-after-send")
        try:
            await writer.enqueue_users(node_id, [service.User(email="slow-user", inbounds=["delta"])])
            await asyncio.wait_for(receiver.delta_landed.wait(), 10)
            worker.stdin.write(b"die\n")
            await worker.stdin.drain()
            await asyncio.wait_for(worker.wait(), 10)
            assert worker.returncode == 1
            # The dead worker's claim is still on record; a full sync must wait it out
            # rather than retire the entry the crashed delivery never acknowledged.
            _, active = await local.capture_queued(node_id)
            assert active == 1
            await node.connect("0.5.4", "26.3.27")
            started = asyncio.get_running_loop().time()
            await manager.sync_full(1, lambda: asyncio.sleep(0, result=[]), flush_pending=False)
            assert asyncio.get_running_loop().time() - started >= 2.0  # waited for the 3s lease
            # After the fence, the surviving record is delivered again on top of the snapshot.
            await wait_until(lambda: receiver.users.get("slow-user") == ["delta"])
            assert receiver.events[-2:] == [("full", []), ("delta", ["slow-user=['delta']"])]
        finally:
            await finish_worker(worker)
            await node.disconnect()
            node.channel.close()
            await node._json_client.close()
            await local.close()
            await writer.close()


@pytest.mark.asyncio
async def test_two_processes_and_the_parent_deliver_a_burst_exactly_once(jetstream):  # noqa: F811
    node_id = "burst-" + uuid4().hex[:6]
    async with receiver_server() as (receiver, port):
        writer = NatsUserSyncStore(jetstream.kv)
        workers = [await start_worker(jetstream, node_id, port, f"worker-{index}", seconds="15") for index in range(2)]
        try:
            expected = {f"user-{number}" for number in range(650)}
            await writer.enqueue_users(node_id, [service.User(email=email, inbounds=["in"]) for email in expected])
            # Wake the processes' lazy workers the way a sibling connect would: their
            # own health poll is not part of this test, so re-enqueue one user.
            await asyncio.sleep(0.2)
            await writer.enqueue_users(node_id, [service.User(email="user-0", inbounds=["in"])])
            await wait_until(lambda: set(receiver.users) >= expected, timeout=40)
            delivered = [email for kind, entries in receiver.events for email in entries]
            assert len(delivered) >= 650
            async with asyncio.timeout(20):
                while (await writer.capture_queued(node_id)) != ({}, 0):
                    await asyncio.sleep(0.05)
            for _, entries in receiver.events:
                assert 1 <= len(entries) <= 100
        finally:
            for worker in workers:
                await finish_worker(worker)
            await writer.close()
