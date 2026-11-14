import asyncio
from unittest.mock import AsyncMock

import pytest

from app.models.node import NodeNotification
from app.notification import connect_node, dedup as notification_dedup, recovered_node


@pytest.fixture(autouse=True)
def _reset_notification_dedup(monkeypatch: pytest.MonkeyPatch):
    notification_dedup._local_claims.clear()
    notification_dedup._kv = None
    notification_dedup._nc = None
    notification_dedup._closed = False
    monkeypatch.setattr(notification_dedup.server_settings, "workers", 4)
    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: False)
    yield
    notification_dedup._local_claims.clear()
    notification_dedup._kv = None
    notification_dedup._nc = None
    notification_dedup._closed = False


@pytest.mark.asyncio
async def test_single_worker_does_not_dedup(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(notification_dedup.server_settings, "workers", 1)
    monkeypatch.setattr(notification_dedup, "_claim_shared", AsyncMock(side_effect=AssertionError("dedup must not run")))
    node = NodeNotification(id=3, name="Hetz Tunnel", node_version="0.5.4", xray_version="26.3.27")
    assert await notification_dedup.claim_notification_slot("connect_node", (node,), {}) is True
    assert await notification_dedup.claim_notification_slot("connect_node", (node,), {}) is True


@pytest.mark.asyncio
async def test_claim_notification_slot_drops_same_event_twice():
    node = NodeNotification(id=3, name="Hetz Tunnel", node_version="0.5.4", xray_version="26.3.27")
    assert await notification_dedup.claim_notification_slot("connect_node", (node,), {}) is True
    assert await notification_dedup.claim_notification_slot("connect_node", (node,), {}) is False


@pytest.mark.asyncio
async def test_safe_notification_wrapper_emits_once(monkeypatch: pytest.MonkeyPatch):
    gathered: list[str] = []

    async def _gather(event_name, *aws):
        gathered.append(event_name)

    async def _enabled():
        class _Node:
            connect = True
            recovered = True

        class _Settings:
            node = _Node()

        return _Settings()

    monkeypatch.setattr("app.notification.notification_enable", _enabled)
    monkeypatch.setattr("app.notification._gather_notifications", _gather)

    node = NodeNotification(id=3, name="Hetz Tunnel", node_version="0.5.4", xray_version="26.3.27")
    await connect_node(node)
    await connect_node(node)
    await recovered_node(node)

    assert gathered == ["connect_node", "recovered_node"]


@pytest.mark.asyncio
async def test_claim_notification_slot_uses_shared_store_across_workers(monkeypatch: pytest.MonkeyPatch):
    notification_dedup._local_claims.clear()
    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    monkeypatch.setattr(notification_dedup, "_claim_shared", AsyncMock(return_value=False))

    node = NodeNotification(id=3, name="Hetz Tunnel", node_version="0.5.4", xray_version="26.3.27")
    assert await notification_dedup.claim_notification_slot("connect_node", (node,), {}) is False


def test_fingerprint_is_stable_for_same_node_event():
    node = NodeNotification(id=3, name="Hetz Tunnel", node_version="0.5.4", xray_version="26.3.27")
    other = NodeNotification(id=3, name="Hetz Tunnel", node_version="0.5.4", xray_version="26.3.27")
    assert notification_dedup.notification_fingerprint("connect_node", (node,), {}) == (
        notification_dedup.notification_fingerprint("connect_node", (other,), {})
    )
    assert notification_dedup.notification_fingerprint("connect_node", (node,), {}) != (
        notification_dedup.notification_fingerprint("error_node", (node,), {})
    )


class _FakeNats:
    def __init__(self, *, is_closed: bool = False, is_connected: bool = True):
        self.is_closed = is_closed
        self.is_connected = is_connected
        self.close = AsyncMock()


def _patch_nats_client(monkeypatch: pytest.MonkeyPatch, clients: list, kv_error: Exception | None = None):
    from app.nats import client as nats_client

    async def _create():
        nc = _FakeNats()
        clients.append(nc)
        return nc

    async def _bucket(js, bucket_name):
        if kv_error is not None:
            raise kv_error
        return object()

    monkeypatch.setattr(nats_client, "create_nats_client", _create)
    monkeypatch.setattr(nats_client, "get_jetstream_context", AsyncMock(return_value=object()))
    monkeypatch.setattr(nats_client, "get_or_create_kv_bucket", _bucket)


@pytest.mark.asyncio
async def test_close_notification_dedup_closes_client_and_is_idempotent(monkeypatch: pytest.MonkeyPatch):
    clients: list[_FakeNats] = []
    _patch_nats_client(monkeypatch, clients)
    kv = await notification_dedup._get_kv()
    assert kv is not None and len(clients) == 1

    await notification_dedup.close_notification_dedup()
    await notification_dedup.close_notification_dedup()

    clients[0].close.assert_awaited_once()
    assert notification_dedup._kv is None


@pytest.mark.asyncio
async def test_close_notification_dedup_without_connection_is_safe():
    await notification_dedup.close_notification_dedup()
    assert notification_dedup._kv is None


@pytest.mark.asyncio
async def test_get_kv_reconnects_only_after_client_is_closed(monkeypatch: pytest.MonkeyPatch):
    clients: list[_FakeNats] = []
    _patch_nats_client(monkeypatch, clients)
    first_kv = await notification_dedup._get_kv()

    # A reconnecting client is not connected but must be kept.
    clients[0].is_connected = False
    assert await notification_dedup._get_kv() is first_kv
    assert len(clients) == 1
    clients[0].close.assert_not_awaited()

    clients[0].is_closed = True
    assert await notification_dedup._get_kv() is not first_kv
    assert len(clients) == 2


@pytest.mark.asyncio
async def test_get_kv_closes_connection_when_bucket_fails(monkeypatch: pytest.MonkeyPatch):
    clients: list[_FakeNats] = []
    _patch_nats_client(monkeypatch, clients, kv_error=RuntimeError("no jetstream"))
    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)

    node = NodeNotification(id=3, name="Hetz Tunnel", node_version="0.5.4", xray_version="26.3.27")
    assert await notification_dedup.claim_notification_slot("connect_node", (node,), {}) is True

    assert len(clients) == 1
    clients[0].close.assert_awaited_once()
    assert notification_dedup._kv is None


@pytest.mark.asyncio
async def test_close_does_not_wait_for_connect_in_progress(monkeypatch: pytest.MonkeyPatch):
    from app.nats import client as nats_client

    _patch_nats_client(monkeypatch, [])
    entered, release = asyncio.Event(), asyncio.Event()
    clients: list[_FakeNats] = []

    async def _hanging_create():
        # Stands in for nats.connect() retrying an unreachable server.
        entered.set()
        await release.wait()
        nc = _FakeNats()
        clients.append(nc)
        return nc

    monkeypatch.setattr(nats_client, "create_nats_client", _hanging_create)
    pending = asyncio.create_task(notification_dedup._get_kv())
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        await asyncio.wait_for(notification_dedup.close_notification_dedup(), timeout=1)
    finally:
        release.set()

    assert await asyncio.wait_for(pending, timeout=1) is None
    assert len(clients) == 1
    clients[0].close.assert_awaited_once()
    assert notification_dedup._kv is None and notification_dedup._nc is None


@pytest.mark.asyncio
async def test_no_connection_is_opened_after_close(monkeypatch: pytest.MonkeyPatch):
    clients: list[_FakeNats] = []
    _patch_nats_client(monkeypatch, clients)
    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    await notification_dedup.close_notification_dedup()

    node = NodeNotification(id=3, name="Hetz Tunnel", node_version="0.5.4", xray_version="26.3.27")
    assert await notification_dedup.claim_notification_slot("connect_node", (node,), {}) is True
    assert await notification_dedup._get_kv() is None
    assert clients == []
