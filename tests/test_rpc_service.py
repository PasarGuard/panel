import json
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.nats import rpc_service as rpc_service_module
from app.nats.rpc_service import BaseRpcService
from app.node.errors import NodeRevocationError
from app.node.worker import NODE_RPC_QUEUE_GROUP, NodeWorkerService
from config import nats_settings


class _FakeSubscription:
    async def unsubscribe(self):
        return None


class _FakeNats:
    def __init__(self):
        self.is_closed = False
        self.subscriptions = []

    async def subscribe(self, subject, *, queue=None, cb):
        self.subscriptions.append((subject, queue, cb))
        return _FakeSubscription()

    async def close(self):
        self.is_closed = True

    async def deliver(self, subject, message):
        grouped = defaultdict(list)
        ungrouped = []
        for registered_subject, queue, callback in self.subscriptions:
            if registered_subject != subject:
                continue
            if queue is None:
                ungrouped.append(callback)
            else:
                grouped[queue].append(callback)

        for callback in ungrouped:
            await callback(message)
        for callbacks in grouped.values():
            await callbacks[0](message)


@pytest.mark.asyncio
async def test_rpc_service_preserves_retryable_error_code():
    service = BaseRpcService("test.rpc", MagicMock(), lambda: True)
    service._dispatch_rpc = AsyncMock(side_effect=NodeRevocationError("node unavailable"))
    message = MagicMock(respond=AsyncMock())

    await service._run_rpc(message, "revoke_users", {})

    assert json.loads(message.respond.await_args.args[0]) == {
        "ok": False,
        "error": "node unavailable",
        "code": 503,
    }


@pytest.mark.asyncio
async def test_node_worker_rpc_subscription_uses_stable_queue_group(monkeypatch):
    connection = _FakeNats()
    monkeypatch.setattr(rpc_service_module, "create_nats_client", AsyncMock(return_value=connection))
    monkeypatch.setattr(rpc_service_module, "is_nats_enabled", lambda: True)
    service = NodeWorkerService()
    service._role_check = lambda: True

    await service.start()

    assert connection.subscriptions[0][:2] == (service._rpc_subject, NODE_RPC_QUEUE_GROUP)
    assert connection.subscriptions[1][:2] == (nats_settings.node_command_subject, None)

    await BaseRpcService.stop(service)


@pytest.mark.asyncio
async def test_rpc_queue_group_delivers_request_to_only_one_service(monkeypatch):
    connection = _FakeNats()
    monkeypatch.setattr(rpc_service_module, "create_nats_client", AsyncMock(return_value=connection))
    monkeypatch.setattr(rpc_service_module, "is_nats_enabled", lambda: True)
    calls = []

    async def handle(instance):
        calls.append(instance)

    services = [BaseRpcService("test.rpc", MagicMock(), lambda: True, queue_group="test.workers") for _ in range(2)]
    for service in services:
        service._handle_rpc = lambda message, service=service: handle(service)
        await service.start()

    await connection.deliver("test.rpc", MagicMock())

    assert calls == [services[0]]

    for service in services:
        await service.stop()


@pytest.mark.asyncio
async def test_rpc_without_queue_group_preserves_broadcast_delivery(monkeypatch):
    connection = _FakeNats()
    monkeypatch.setattr(rpc_service_module, "create_nats_client", AsyncMock(return_value=connection))
    monkeypatch.setattr(rpc_service_module, "is_nats_enabled", lambda: True)
    calls = []

    async def handle(instance):
        calls.append(instance)

    services = [BaseRpcService("test.rpc", MagicMock(), lambda: True) for _ in range(2)]
    for service in services:
        service._handle_rpc = lambda message, service=service: handle(service)
        await service.start()

    await connection.deliver("test.rpc", MagicMock())

    assert calls == services

    for service in services:
        await service.stop()
