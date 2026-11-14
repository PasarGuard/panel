from unittest.mock import AsyncMock

import pytest

from app.models.node import NodeNotification
from app.notification import connect_node, dedup as notification_dedup, recovered_node


@pytest.fixture(autouse=True)
def _reset_notification_dedup(monkeypatch: pytest.MonkeyPatch):
    notification_dedup._local_claims.clear()
    notification_dedup._shared_claims.clear()
    notification_dedup._shared_claims_kv = None
    notification_dedup._nc = None
    notification_dedup._kv = None
    monkeypatch.setattr(notification_dedup.server_settings, "workers", 4)
    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: False)
    yield
    notification_dedup._local_claims.clear()
    notification_dedup._shared_claims.clear()
    notification_dedup._shared_claims_kv = None
    notification_dedup._nc = None
    notification_dedup._kv = None


@pytest.mark.asyncio
async def test_single_worker_does_not_dedup(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(notification_dedup.server_settings, "workers", 1)
    monkeypatch.setattr(
        notification_dedup, "_claim_shared", AsyncMock(side_effect=AssertionError("dedup must not run"))
    )
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


@pytest.mark.asyncio
async def test_get_kv_reconnects_when_nc_closed_or_disconnected_and_closes_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
):
    from types import SimpleNamespace

    from app.nats.kv_cas import MemoryCasKv

    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)

    nc1 = SimpleNamespace(is_closed=False, is_connected=True, close=AsyncMock())
    kv1 = MemoryCasKv()
    nc2 = SimpleNamespace(is_closed=False, is_connected=True, close=AsyncMock())
    kv2 = MemoryCasKv()
    nc3 = SimpleNamespace(is_closed=False, is_connected=True, close=AsyncMock())
    kv3 = MemoryCasKv()

    setup_mock = AsyncMock(side_effect=[(nc1, None, kv1), (nc2, None, kv2), (nc3, None, kv3)])
    monkeypatch.setattr("app.nats.client.setup_nats_kv", setup_mock)

    try:
        assert await notification_dedup._get_kv() is kv1
        assert notification_dedup._nc is nc1
        assert setup_mock.await_count == 1

        # Healthy connection is reused without reconnecting
        assert await notification_dedup._get_kv() is kv1
        assert setup_mock.await_count == 1

        # Disconnected client closes old nc and reconnects cleanly
        nc1.is_connected = False
        assert await notification_dedup._get_kv() is kv2
        nc1.close.assert_awaited_once()
        assert notification_dedup._nc is nc2
        assert setup_mock.await_count == 2

        # Closed client resets and reconnects without re-closing an already-closed nc
        nc2.is_closed = True
        assert await notification_dedup._get_kv() is kv3
        nc2.close.assert_not_awaited()
        assert notification_dedup._nc is nc3
        assert setup_mock.await_count == 3

        # Shutdown helper closes active client and resets _nc/_kv
        await notification_dedup.close_notification_dedup()
        nc3.close.assert_awaited_once()
        assert notification_dedup._nc is None
        assert notification_dedup._kv is None
    finally:
        await notification_dedup.close_notification_dedup()


def test_app_factory_registers_close_notification_dedup_on_shutdown(monkeypatch: pytest.MonkeyPatch):
    from app import app_factory
    from app.nats import leader
    from role import Role

    registered_shutdown: list = []
    monkeypatch.setattr(app_factory, "on_startup", lambda fn: fn)
    monkeypatch.setattr(app_factory, "on_shutdown", lambda fn: registered_shutdown.append(fn) or fn)
    monkeypatch.setattr(leader, "set_on_leadership_lost", lambda _cb: None)

    monkeypatch.setattr(app_factory.runtime_settings, "role", Role.BACKEND)
    app_factory._register_scheduler_hooks()
    assert notification_dedup.close_notification_dedup in registered_shutdown

    registered_shutdown.clear()
    monkeypatch.setattr(app_factory.runtime_settings, "role", Role.ALL_IN_ONE)
    app_factory._register_scheduler_hooks()
    assert notification_dedup.close_notification_dedup in registered_shutdown


@pytest.mark.asyncio
async def test_shared_kv_prunes_expired_keys_without_keys_scan_and_preserves_live_claims(
    monkeypatch: pytest.MonkeyPatch,
):
    from app.nats.kv_cas import MemoryCasKv, kv_cas_json, kv_get_json

    kv = MemoryCasKv()
    monkeypatch.setattr(
        kv,
        "keys",
        AsyncMock(side_effect=AssertionError("kv.keys() must never be called")),
    )
    # Seed an unrelated leader key in the shared bucket to prove it is never touched.
    await kv.create("job_leader.all-in-one", b'{"token":"leader-1","expires_at":9999999999}')

    notification_dedup._kv = kv
    notification_dedup._nc = None
    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)

    t0 = 1_000_000.0
    monkeypatch.setattr(notification_dedup.time, "time", lambda: t0)

    node_a = NodeNotification(id=1, name="A", node_version="0.5.4", xray_version="26.3.27")
    node_b = NodeNotification(id=2, name="B", node_version="0.5.4", xray_version="26.3.27")
    node_c = NodeNotification(id=3, name="C", node_version="0.5.4", xray_version="26.3.27")

    key_a = notification_dedup.notification_fingerprint("connect_node", (node_a,), {})
    key_b = notification_dedup.notification_fingerprint("connect_node", (node_b,), {})

    assert await notification_dedup.claim_notification_slot("connect_node", (node_a,), {}) is True
    assert await notification_dedup.claim_notification_slot("connect_node", (node_b,), {}) is True
    assert key_a in kv._data
    assert key_b in kv._data

    # Simulate another worker refreshing key_b right before our local expiry window passes.
    _, rev_b = await kv_get_json(kv, key_b)
    t1 = t0 + notification_dedup.DEDUP_WINDOW_SECONDS + 1.0
    assert await kv_cas_json(kv, key_b, {"expires_at": t1 + notification_dedup.DEDUP_WINDOW_SECONDS}, rev_b)

    # Advance past t0's window and claim node_c: expired key_a is deleted, refreshed live key_b is kept!
    monkeypatch.setattr(notification_dedup.time, "time", lambda: t1)
    assert await notification_dedup.claim_notification_slot("connect_node", (node_c,), {}) is True

    assert key_a not in kv._data
    assert key_b in kv._data
    assert "job_leader.all-in-one" in kv._data
    # Live claim on key_b must still block emission on another worker at t1.
    notification_dedup._local_claims.clear()
    assert await notification_dedup.claim_notification_slot("connect_node", (node_b,), {}) is False


@pytest.mark.asyncio
async def test_local_claims_stay_bounded_and_fake_kv_without_delete_is_safe(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(notification_dedup, "MAX_LOCAL_CLAIMS", 4)
    monkeypatch.setattr(notification_dedup.time, "time", lambda: 5_000.0)

    for idx in range(10):
        assert await notification_dedup.claim_notification_slot("custom_event", (idx,), {}) is True

    assert len(notification_dedup._local_claims) <= 4

    # Minimal fake KV without .delete/.get (e.g. when kv_get_json/kv_cas_json are patched directly)
    notification_dedup._local_claims.clear()
    notification_dedup._kv = object()
    notification_dedup._nc = None
    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    monkeypatch.setattr(notification_dedup, "kv_get_json", AsyncMock(return_value=(None, 0)))
    monkeypatch.setattr(notification_dedup, "kv_cas_json", AsyncMock(return_value=True))

    monkeypatch.setattr(notification_dedup.time, "time", lambda: 6_000.0)
    assert await notification_dedup.claim_notification_slot("custom_event", ("one",), {}) is True
    monkeypatch.setattr(notification_dedup.time, "time", lambda: 6_020.0)
    assert await notification_dedup.claim_notification_slot("custom_event", ("two",), {}) is True
