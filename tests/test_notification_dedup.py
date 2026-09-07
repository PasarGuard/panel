import pytest

from app.models.node import NodeNotification
from app.notification import connect_node, dedup as notification_dedup, recovered_node


@pytest.fixture(autouse=True)
def _reset_notification_dedup(monkeypatch: pytest.MonkeyPatch):
    notification_dedup._local_claims.clear()
    notification_dedup._kv = None
    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: False)
    yield
    notification_dedup._local_claims.clear()


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
