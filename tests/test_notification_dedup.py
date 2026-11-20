import asyncio
from datetime import UTC, datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import notification
from app.db.models import UserStatus
from app.models.admin import AdminDetails
from app.models.node import NodeNotification
from app.models.user import UserNotificationResponse
from app.notification import connect_node, dedup as notification_dedup, recovered_node


@pytest.fixture(autouse=True)
def _reset_notification_dedup(monkeypatch: pytest.MonkeyPatch):
    notification_dedup._local_claims.clear()
    notification_dedup._kv = None
    notification_dedup._nc = None
    notification_dedup._closed = False
    notification_dedup._retry_at = 0.0
    notification_dedup._bucket_warned = False
    # pytest-asyncio gives every test its own loop; a lock that was waited on is bound to the old one.
    monkeypatch.setattr(notification_dedup, "_kv_lock", asyncio.Lock())
    monkeypatch.setattr(notification_dedup.server_settings, "workers", 4)
    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: False)
    yield
    notification_dedup._local_claims.clear()
    notification_dedup._kv = None
    notification_dedup._nc = None
    notification_dedup._closed = False
    notification_dedup._retry_at = 0.0


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

    async def _bucket(js, bucket_name, **options):
        if kv_error is not None:
            raise kv_error
        return object()

    monkeypatch.setattr(notification_dedup, "_connect_nats", _create)
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

    monkeypatch.setattr(notification_dedup, "_connect_nats", _hanging_create)
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


def _node(node_id: int) -> NodeNotification:
    return NodeNotification(id=node_id, name=f"node-{node_id}", node_version="0.5.4", xray_version="26.3.27")


@pytest.mark.asyncio
async def test_unreachable_nats_does_not_queue_or_retry_every_notification(monkeypatch: pytest.MonkeyPatch):
    from app.nats import client as nats_client
    from app.nats.kv_cas import MemoryCasKv

    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    connect_delay = 0.3
    attempts: list[dict] = []
    nats_up = False
    shared_kv = MemoryCasKv()

    async def _create():
        attempts.append(1)
        if not nats_up:
            # Stands in for one connect attempt timing out against an unreachable server.
            await asyncio.sleep(connect_delay)
            raise OSError("connection refused")
        return _FakeNats()

    async def _bucket(js, bucket_name, **options):
        return shared_kv

    monkeypatch.setattr(notification_dedup, "_connect_nats", _create)
    monkeypatch.setattr(nats_client, "get_jetstream_context", AsyncMock(return_value=object()))
    monkeypatch.setattr(nats_client, "get_or_create_kv_bucket", _bucket)

    loop = asyncio.get_running_loop()
    started = loop.time()
    results = await asyncio.gather(
        *(notification_dedup.claim_notification_slot("connect_node", (_node(i),), {}) for i in range(10))
    )
    elapsed = loop.time() - started

    assert results == [True] * 10
    assert elapsed < connect_delay * 2, f"notifications queued behind the connect: {elapsed:.2f}s"
    assert len(attempts) == 1

    # During the back-off a notification returns at once without a new connect attempt.
    started = loop.time()
    assert await notification_dedup.claim_notification_slot("connect_node", (_node(100),), {}) is True
    assert loop.time() - started < connect_delay / 2
    assert len(attempts) == 1

    # NATS is back and the back-off is over: the shared check drops another worker's duplicate again.
    nats_up = True
    monkeypatch.setattr(notification_dedup, "_retry_at", 0.0)
    assert await notification_dedup.claim_notification_slot("connect_node", (_node(200),), {}) is True
    notification_dedup._local_claims.clear()  # the same event seen by another worker
    assert await notification_dedup.claim_notification_slot("connect_node", (_node(200),), {}) is False
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_hanging_kv_call_is_bounded_and_backs_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    monkeypatch.setattr(notification_dedup, "_KV_TIMEOUT_SECONDS", 0.2)
    calls = 0

    class _HangingKv:
        async def get(self, key):
            nonlocal calls
            calls += 1
            await asyncio.sleep(30)

    notification_dedup._kv = _HangingKv()
    notification_dedup._nc = _FakeNats()

    loop = asyncio.get_running_loop()
    started = loop.time()
    assert await notification_dedup.claim_notification_slot("connect_node", (_node(1),), {}) is True
    assert loop.time() - started < 1
    assert await notification_dedup.claim_notification_slot("connect_node", (_node(2),), {}) is True
    assert calls == 1


@pytest.mark.asyncio
async def test_real_connect_to_unreachable_nats_gives_up_quickly(monkeypatch: pytest.MonkeyPatch):
    import socket

    import app.nats

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    monkeypatch.setattr(app.nats, "get_nats_config", lambda: {"url": f"nats://127.0.0.1:{port}"})

    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(Exception) as exc_info:
        # nats-py defaults retry the first connect 60 times, two seconds apart.
        await asyncio.wait_for(notification_dedup._get_kv(), timeout=6)
    assert not isinstance(exc_info.value, TimeoutError)
    assert loop.time() - started < 3.5
    assert notification_dedup._backing_off()


@pytest.mark.asyncio
async def test_connect_in_progress_makes_concurrent_notifications_wait_for_the_shared_check(
    monkeypatch: pytest.MonkeyPatch,
):
    from app.nats import client as nats_client
    from app.nats.kv_cas import MemoryCasKv

    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    shared_kv = MemoryCasKv()
    connects = 0

    async def _create():
        nonlocal connects
        connects += 1
        await asyncio.sleep(0.2)  # a cold-start connect to a working NATS
        return _FakeNats()

    async def _bucket(js, bucket_name, **options):
        return shared_kv

    monkeypatch.setattr(notification_dedup, "_connect_nats", _create)
    monkeypatch.setattr(nats_client, "get_jetstream_context", AsyncMock(return_value=object()))
    monkeypatch.setattr(nats_client, "get_or_create_kv_bucket", _bucket)

    events = [notification_dedup.claim_notification_slot("connect_node", (_node(i),), {}) for i in range(20)]
    assert await asyncio.gather(*events) == [True] * 20
    assert connects == 1
    assert len(shared_kv._data) == 20

    # Another worker sees the same 20 events: every one is dropped by the shared check.
    notification_dedup._local_claims.clear()
    events = [notification_dedup.claim_notification_slot("connect_node", (_node(i),), {}) for i in range(20)]
    assert await asyncio.gather(*events) == [False] * 20


def _use_kv(kv) -> None:
    notification_dedup._kv = kv
    notification_dedup._nc = _FakeNats()


async def _put_claim(kv, key: str, expires_at: float) -> None:
    from app.nats.kv_cas import kv_put_json

    await kv_put_json(kv, key, {"expires_at": expires_at})


@pytest.mark.asyncio
async def test_expired_key_removed_between_get_and_update_is_not_a_duplicate(monkeypatch: pytest.MonkeyPatch):
    import time

    from app.nats.kv_cas import MemoryCasKv

    class _ExpiringKv(MemoryCasKv):
        # NATS removes the expired message (bucket max_age) right after it was read.
        async def get(self, key):
            entry = await super().get(key)
            self._data.pop(key, None)
            return entry

    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    kv = _ExpiringKv()
    key = notification_dedup.notification_fingerprint("connect_node", (_node(1),), {})
    await _put_claim(kv, key, time.time() - 1)
    _use_kv(kv)

    assert await notification_dedup.claim_notification_slot("connect_node", (_node(1),), {}) is True
    assert key in kv._data


@pytest.mark.asyncio
async def test_failed_kv_write_is_not_a_duplicate(monkeypatch: pytest.MonkeyPatch):
    import nats.errors as nats_errors

    from app.nats.kv_cas import MemoryCasKv

    class _BrokenWriteKv(MemoryCasKv):
        async def create(self, key, value):
            raise nats_errors.NoRespondersError

    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    _use_kv(_BrokenWriteKv())

    assert await notification_dedup.claim_notification_slot("connect_node", (_node(1),), {}) is True
    # A failed write is an outage, not a lost race: the next events skip the store for a while.
    assert notification_dedup._backing_off()


class _RacedKv:
    """Both CAS attempts lose: the expired key is removed, then another worker creates a live claim."""

    def __init__(self, key: str, expired_at: float, live_until: float):
        import json

        self._key = key
        self._live = json.dumps({"expires_at": live_until}).encode()
        self._docs = [(json.dumps({"expires_at": expired_at}).encode(), 5), None]
        self.final_get = None

    async def get(self, key):
        import nats.js.errors as nats_js_errors
        from nats.js.kv import KeyValue

        if self._docs:
            doc = self._docs.pop(0)
        elif self.final_get is not None:
            return await self.final_get()
        else:
            doc = (self._live, 6)
        if doc is None:
            raise nats_js_errors.KeyNotFoundError
        return KeyValue.Entry(bucket="", key=key, value=doc[0], revision=doc[1], delta=0, created=None, operation=None)

    async def create(self, key, value, **kwargs):
        import nats.js.errors as nats_js_errors

        raise nats_js_errors.KeyWrongLastSequenceError("wrong last sequence")

    update = create


@pytest.mark.asyncio
async def test_live_claim_created_after_the_last_lost_cas_is_a_duplicate(monkeypatch: pytest.MonkeyPatch):
    import time

    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    key = notification_dedup.notification_fingerprint("connect_node", (_node(1),), {})
    _use_kv(_RacedKv(key, time.time() - 1, time.time() + 10))

    assert await notification_dedup.claim_notification_slot("connect_node", (_node(1),), {}) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["error", "hang"])
async def test_failed_recheck_after_lost_cas_still_sends(monkeypatch: pytest.MonkeyPatch, failure: str):
    import time

    import nats.errors as nats_errors

    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    monkeypatch.setattr(notification_dedup, "_KV_TIMEOUT_SECONDS", 0.2)
    key = notification_dedup.notification_fingerprint("connect_node", (_node(1),), {})
    kv = _RacedKv(key, time.time() - 1, time.time() + 10)

    async def _final_get():
        if failure == "error":
            raise nats_errors.NoRespondersError
        await asyncio.sleep(10)

    kv.final_get = _final_get
    _use_kv(kv)

    assert await notification_dedup.claim_notification_slot("connect_node", (_node(1),), {}) is True
    assert notification_dedup._backing_off()


@pytest.mark.asyncio
async def test_stuck_close_does_not_hold_the_connect_lock(monkeypatch: pytest.MonkeyPatch):
    clients: list[_FakeNats] = []
    _patch_nats_client(monkeypatch, clients, kv_error=RuntimeError("no jetstream"))
    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    monkeypatch.setattr(notification_dedup, "_CONNECT_TIMEOUT_SECONDS", 0.1)

    async def _stuck_close():
        await asyncio.sleep(10)

    original = notification_dedup._connect_nats

    async def _create():
        nc = await original()
        nc.close = _stuck_close
        return nc

    monkeypatch.setattr(notification_dedup, "_connect_nats", _create)

    claim = notification_dedup.claim_notification_slot("connect_node", (_node(1),), {})
    assert await asyncio.wait_for(claim, timeout=2) is True
    assert not notification_dedup._kv_lock.locked()


@pytest.mark.asyncio
async def test_hanging_connect_is_bounded_as_a_whole(monkeypatch: pytest.MonkeyPatch):
    import nats

    import app.nats

    created: list = []

    class _UpgradeHangsNats:
        def __init__(self):
            self.close = AsyncMock()
            created.append(self)

        async def connect(self, url, **options):
            # ws://: aiohttp waits for the HTTP upgrade with its 300s session timeout.
            await asyncio.sleep(10)

    monkeypatch.setattr(nats, "NATS", _UpgradeHangsNats)
    monkeypatch.setattr(app.nats, "get_nats_config", lambda: {"url": "ws://example:8080"})
    monkeypatch.setattr(notification_dedup, "_CONNECT_TOTAL_TIMEOUT_SECONDS", 0.2)

    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(notification_dedup._get_kv(), timeout=2)
    assert loop.time() - started < 1

    created[0].close.assert_awaited_once()
    assert notification_dedup._backing_off()


@pytest.mark.asyncio
async def test_live_claim_by_another_worker_is_still_a_duplicate(monkeypatch: pytest.MonkeyPatch):
    import time

    from app.nats.kv_cas import MemoryCasKv

    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    kv = MemoryCasKv()
    key = notification_dedup.notification_fingerprint("connect_node", (_node(1),), {})
    await _put_claim(kv, key, time.time() + 10)
    _use_kv(kv)

    assert await notification_dedup.claim_notification_slot("connect_node", (_node(1),), {}) is False


@pytest.mark.asyncio
async def test_failed_handshake_closes_the_connection(monkeypatch: pytest.MonkeyPatch):
    import nats

    import app.nats

    created: list = []

    class _HandshakeFailsNats:
        def __init__(self):
            self.options = None
            self.close = AsyncMock()
            created.append(self)

        async def connect(self, url, **options):
            # TCP is up, but INFO/PONG never comes.
            self.options = options
            raise TimeoutError

    monkeypatch.setattr(nats, "NATS", _HandshakeFailsNats)
    monkeypatch.setattr(app.nats, "get_nats_config", lambda: {"url": "nats://example:4222"})

    with pytest.raises(TimeoutError):
        await notification_dedup._get_kv()

    assert len(created) == 1
    created[0].close.assert_awaited_once()
    assert created[0].options["allow_reconnect"] is False
    assert created[0].options["connect_timeout"] <= 1
    assert notification_dedup._backing_off()


class _RecordingJs:
    def __init__(self):
        self.created: list[dict] = []

    async def create_key_value(self, **params):
        self.created.append(params)
        return object()


@pytest.mark.asyncio
async def test_dedup_keys_go_to_own_bucket_with_ttl(monkeypatch: pytest.MonkeyPatch):
    from app.nats import client as nats_client
    from config import nats_settings

    js = _RecordingJs()

    async def _create():
        return _FakeNats()

    monkeypatch.setattr(notification_dedup, "_connect_nats", _create)
    monkeypatch.setattr(nats_client, "get_jetstream_context", AsyncMock(return_value=js))

    assert await notification_dedup._get_kv() is not None
    assert js.created == [
        {"bucket": nats_settings.notification_dedup_kv_bucket, "ttl": notification_dedup.DEDUP_KEY_TTL_SECONDS}
    ]
    assert nats_settings.notification_dedup_kv_bucket != nats_settings.scheduler_leader_kv_bucket
    assert notification_dedup.DEDUP_KEY_TTL_SECONDS >= notification_dedup.DEDUP_WINDOW_SECONDS


@pytest.mark.asyncio
async def test_scheduler_leader_bucket_is_created_without_ttl(monkeypatch: pytest.MonkeyPatch):
    from app.nats import client as nats_client, leader
    from config import nats_settings

    js = _RecordingJs()
    monkeypatch.setattr(leader, "create_nats_client", AsyncMock(return_value=_FakeNats()))
    monkeypatch.setattr(leader, "get_jetstream_context", AsyncMock(return_value=js))
    monkeypatch.setattr(leader, "is_nats_enabled", lambda: True)
    monkeypatch.setattr(leader, "_nc", None)
    monkeypatch.setattr(leader, "_kv", None)

    await leader._ensure_kv()
    await nats_client.get_or_create_kv_bucket(js, "other_bucket")

    assert js.created == [{"bucket": nats_settings.scheduler_leader_kv_bucket}, {"bucket": "other_bucket"}]


@pytest.mark.asyncio
async def test_unavailable_dedup_bucket_is_warned_once_per_outage(monkeypatch: pytest.MonkeyPatch):
    from unittest.mock import Mock

    clients: list[_FakeNats] = []
    _patch_nats_client(monkeypatch, clients, kv_error=RuntimeError("permissions violation"))
    monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
    log = Mock()
    monkeypatch.setattr(notification_dedup, "logger", log)

    for i in range(3):
        notification_dedup._retry_at = 0.0  # the back-off is over
        assert await notification_dedup.claim_notification_slot("connect_node", (_node(i),), {}) is True

    assert len(clients) == 3
    assert log.warning.call_count == 1

    # The bucket is back, then lost again: that outage is reported too.
    _patch_nats_client(monkeypatch, clients)
    notification_dedup._retry_at = 0.0
    assert await notification_dedup._get_kv() is not None
    clients[-1].is_closed = True
    _patch_nats_client(monkeypatch, clients, kv_error=RuntimeError("permissions violation"))
    assert await notification_dedup.claim_notification_slot("connect_node", (_node(9),), {}) is True
    assert log.warning.call_count == 2


def _event_settings(enabled: bool = True) -> SimpleNamespace:
    flags = SimpleNamespace(
        modify=enabled,
        status_change=enabled,
        login=enabled,
        usage_limit_warning=enabled,
        connect=enabled,
        limited=enabled,
    )
    return SimpleNamespace(user=flags, admin=flags, node=flags)


def _user(**overrides) -> UserNotificationResponse:
    data = {
        "id": 7,
        "username": "alice",
        "status": UserStatus.active,
        "used_traffic": 0,
        "data_limit": 10 * 1024**3,
        "created_at": dt(2026, 11, 1, tzinfo=UTC),
    } | overrides
    return UserNotificationResponse(**data)


class _Workers:
    """Uvicorn workers sharing one dedup store, each with its own in-process claims."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, enabled: bool = True):
        self.sent: list[str] = []
        self.store: dict[str, float] = {}
        self.local: dict[str, dict[str, float]] = {}
        self.now = 1_000_000.0
        self.shared_claims = 0
        self.current: str | None = None

        async def _gather(event_name, *aws):
            for aw in aws:
                aw.close()
            self.sent.append(event_name)

        async def _enabled():
            return _event_settings(enabled)

        async def _claim_shared(key, now):
            self.shared_claims += 1
            if self.store.get(key, 0) > now:
                return False
            self.store[key] = now + notification_dedup.DEDUP_WINDOW_SECONDS
            return True

        monkeypatch.setattr("app.notification.notification_enable", _enabled)
        monkeypatch.setattr("app.notification._gather_notifications", _gather)
        monkeypatch.setattr(notification_dedup, "is_nats_enabled", lambda: True)
        monkeypatch.setattr(notification_dedup, "_claim_shared", _claim_shared)
        monkeypatch.setattr(notification_dedup.time, "time", lambda: self.now)

    def on(self, worker: str) -> _Workers:
        claims = notification_dedup._local_claims
        if self.current is not None:
            self.local[self.current] = dict(claims)
        claims.clear()
        claims.update(self.local.get(worker, {}))
        self.current = worker
        return self


@pytest.mark.asyncio
async def test_distinct_changes_of_one_user_within_the_window_are_all_sent(monkeypatch: pytest.MonkeyPatch):
    workers = _Workers(monkeypatch)
    by = AdminDetails(username="root", is_sudo=True)
    # Four API edits of one user at 0, 3, 6 and 14 s, each handled by whichever worker got the request.
    for second, (worker, limit) in zip((0, 3, 6, 14), (("a", 10), ("b", 20), ("a", 30), ("c", 40))):
        workers.now = 1_000_000.0 + second
        workers.on(worker)
        await notification.modify_user(_user(data_limit=limit * 1024**3), by)
        await notification.user_status_change(_user(data_limit=limit * 1024**3), by)

    assert workers.sent == ["modify_user", "user_status_change"] * 4


@pytest.mark.asyncio
async def test_repeated_identical_request_events_are_all_sent(monkeypatch: pytest.MonkeyPatch):
    workers = _Workers(monkeypatch).on("a")
    by = AdminDetails(username="root", is_sudo=True)
    # A user disabled and enabled again, and two failed logins with the same password: separate events.
    await notification.user_status_change(_user(status=UserStatus.active), by)
    await notification.user_status_change(_user(status=UserStatus.disabled), by)
    await notification.user_status_change(_user(status=UserStatus.active), by)
    await notification.admin_login("root", "wrong", "10.0.0.1", False)
    await notification.admin_login("root", "wrong", "10.0.0.1", False)

    assert workers.sent == ["user_status_change"] * 3 + ["admin_login"] * 2
    assert workers.shared_claims == 0


@pytest.mark.asyncio
async def test_one_event_reported_by_two_workers_is_sent_once(monkeypatch: pytest.MonkeyPatch):
    workers = _Workers(monkeypatch)
    node = _node(3)
    # Every worker connects the nodes at startup and reports the same connect.
    workers.on("a")
    await connect_node(node)
    workers.now += 0.2
    workers.on("b")
    await connect_node(NodeNotification(**node.model_dump()))

    assert workers.sent == ["connect_node"]


@pytest.mark.asyncio
async def test_identical_event_after_the_window_is_sent_again(monkeypatch: pytest.MonkeyPatch):
    workers = _Workers(monkeypatch)
    node = _node(3)
    workers.on("a")
    await connect_node(node)
    workers.now += notification_dedup.DEDUP_WINDOW_SECONDS + 1
    workers.on("b")
    await connect_node(node)

    assert workers.sent == ["connect_node", "connect_node"]


@pytest.mark.asyncio
async def test_background_events_with_different_payloads_are_not_merged(monkeypatch: pytest.MonkeyPatch):
    workers = _Workers(monkeypatch).on("a")
    admin = AdminDetails(username="reseller", is_sudo=False, used_traffic=900)
    await notification.admin_usage_limit_reached(admin, 80, 80)
    await notification.admin_usage_limit_reached(admin, 90, 90)
    await notification.limited_node(_node(3), 100, 100)
    await notification.limited_node(_node(3), 100, 120)

    assert workers.sent == ["admin_usage_limit_reached"] * 2 + ["limited_node"] * 2


@pytest.mark.asyncio
async def test_disabled_event_does_not_touch_the_dedup_store(monkeypatch: pytest.MonkeyPatch):
    workers = _Workers(monkeypatch, enabled=False).on("a")
    await connect_node(_node(3))
    await notification.limited_node(_node(3), 100, 120)
    await notification.admin_usage_limit_reached(AdminDetails(username="reseller", is_sudo=False), 80, 80)

    assert workers.sent == []
    assert workers.shared_claims == 0
    assert notification_dedup._local_claims == {}


def test_fingerprint_tells_apart_changes_of_one_object():
    user = _user(data_limit=1)
    a = notification_dedup.notification_fingerprint("modify_user", (user,), {})
    b = notification_dedup.notification_fingerprint("modify_user", (user.model_copy(update={"data_limit": 2}),), {})
    # Another worker builds its own copy of the same state.
    same = notification_dedup.notification_fingerprint("modify_user", (user.model_copy(deep=True),), {})
    assert a != b
    assert a == same


@pytest.mark.asyncio
async def test_event_that_cannot_be_fingerprinted_is_still_sent(monkeypatch):
    monkeypatch.setattr(notification_dedup.server_settings, "workers", 4)

    def _broken(*_args, **_kwargs):
        raise ValueError("unserializable payload")

    monkeypatch.setattr(notification_dedup, "notification_fingerprint", _broken)
    assert await notification_dedup.claim_notification_slot("connect_node", (object(),), {}) is True
