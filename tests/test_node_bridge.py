import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import certifi
import pytest
from PasarGuardNodeBridge import InMemoryUserSyncStore, NodeType
from PasarGuardNodeBridge.common.service_pb2 import User
from PasarGuardNodeBridge.grpclib import Node as GrpcNode
from PasarGuardNodeBridge.rest import Node as RestNode

from app.node.bridge import create_node


def make_node(transport):
    return create_node(
        connection=NodeType(transport),
        address="localhost",
        port=1,
        api_port=1,
        server_ca=certifi.contents(),
        api_key=str(uuid4()),
        node_id=uuid4().hex,
        user_sync_store=InMemoryUserSyncStore(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["grpc", "rest"])
async def test_explicit_per_user_fallback_still_uses_original_transport(monkeypatch, transport):
    node = make_node(transport)
    base = GrpcNode if transport == "grpc" else RestNode
    users = [User(email="retry")]
    fallback = AsyncMock(return_value=users)
    monkeypatch.setattr(base, "_sync_batch_users", fallback)
    chunked = AsyncMock(return_value=[])
    monkeypatch.setattr(node, "sync_users_chunked", chunked)
    try:
        await node.connect("0.5.4", "26.3.27")
        assert await node._sync_batch_users(users) is users
        fallback.assert_awaited_once_with(users)
        chunked.assert_not_awaited()
    finally:
        await node.disconnect()
        if hasattr(node, "channel"):
            node.channel.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["grpc", "rest"])
async def test_queued_sync_keeps_legacy_node_protocol(monkeypatch, transport):
    node = make_node(transport)
    base = GrpcNode if transport == "grpc" else RestNode
    node._worker_idle_timeout = 0.01
    node._sync_poll_interval = 0.01
    fallback = AsyncMock(return_value=[])
    monkeypatch.setattr(base, "_sync_batch_users", fallback)
    chunked = AsyncMock(return_value=[])
    monkeypatch.setattr(node, "sync_users_chunked", chunked)
    try:
        await node.connect("0.1.0", "26.3.27")
        await node.update_users([User(email="legacy")])
        await asyncio.wait_for(node._sync_worker_task, timeout=5)
        assert fallback.await_args.args[0][0].email == "legacy"
        chunked.assert_not_awaited()
    finally:
        await node.disconnect()
        if hasattr(node, "channel"):
            node.channel.close()
