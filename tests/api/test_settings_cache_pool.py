"""Cached settings on the /sub path must not need a second pooled connection per request."""

import asyncio
import copy
from collections import Counter

import pytest
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Settings
from app.models.client_template import ClientTemplateType
from app.models.settings import SettingsSchema
from app.operation import OperatorType
from app.operation.client_template import ClientTemplateOperation
from app.operation.settings import SettingsOperation
from app.routers import subscription as subscription_router
from app.routers.dependencies.subscription import warm_subscription_caches
from app.settings import (
    cleanup_settings,
    general_settings,
    hwid_settings,
    notification_enable,
    notification_settings,
    refresh_caches,
    subscription_settings,
    telegram_settings,
    webhook_settings,
)
from app.subscription.client_templates import (
    subscription_client_templates,
    subscription_happ_routing_templates,
    subscription_xray_templates,
)
from app.utils.jwt import get_secret_key

from . import client

CACHES = (
    telegram_settings,
    webhook_settings,
    notification_settings,
    notification_enable,
    subscription_settings,
    hwid_settings,
    general_settings,
    cleanup_settings,
    subscription_client_templates,
    subscription_xray_templates,
    subscription_happ_routing_templates,
    get_secret_key,
)


@pytest.fixture
def cold_caches():
    for cache in CACHES:
        cache.clear()
    yield
    # Later tests reload from their own patched sessions instead of these fakes.
    for cache in CACHES:
        cache.clear()


@pytest.fixture
async def small_pool(tmp_path, monkeypatch, mock_settings):
    """A real QueuePool of 2 connections behind every cached loader, counting DB reads."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'pool.db'}", pool_size=2, max_overflow=0, pool_timeout=1
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    reads: Counter[str] = Counter()
    row = {"settings": Settings(**copy.deepcopy(mock_settings))}

    async def read(db, kind):
        await db.execute(text("SELECT 1"))
        reads[kind] += 1

    async def fake_get_settings(db):
        await read(db, "settings")
        return row["settings"]

    async def fake_client_template_values(db):
        await read(db, "client_templates")
        return {}

    async def fake_xray_templates(db, template_type):
        is_xray = template_type == ClientTemplateType.xray_subscription
        await read(db, "xray_templates" if is_xray else "happ_routing_templates")
        return {}

    async def fake_secret_key(db):
        await read(db, "secret_key")
        return "secret"

    for module in ("app.settings", "app.subscription.client_templates", "app.utils.jwt"):
        monkeypatch.setattr(f"{module}.GetDB", session_factory)
    monkeypatch.setattr("app.settings.get_settings", fake_get_settings)
    monkeypatch.setattr("app.subscription.client_templates.get_client_template_values", fake_client_template_values)
    monkeypatch.setattr("app.subscription.client_templates.get_client_template_contents_by_type", fake_xray_templates)
    monkeypatch.setattr("app.utils.jwt.get_jwt_secret_key", fake_secret_key)
    yield session_factory, reads, row
    await engine.dispose()


async def _read_sub_caches():
    await subscription_settings()
    await hwid_settings()
    await get_secret_key()
    await subscription_client_templates()
    await subscription_xray_templates()


def test_subscription_router_warms_caches_before_handlers():
    deps = [dep.dependency for dep in subscription_router.router.dependencies]
    assert warm_subscription_caches in deps


async def test_cold_cache_concurrent_reads_hit_database_once(cold_caches, small_pool):
    _, reads, _ = small_pool

    await asyncio.gather(*(_read_sub_caches() for _ in range(20)))

    assert reads == {"settings": 2, "secret_key": 1, "client_templates": 1, "xray_templates": 1}


async def test_cold_cache_sub_requests_survive_pool_smaller_than_requests(cold_caches, small_pool):
    session_factory, reads, _ = small_pool

    async def sub_request():
        await warm_subscription_caches()  # router-level dependency of every /sub route
        async with session_factory() as db:
            await db.execute(text("SELECT 1"))  # the user lookup: the request now holds a connection
            await asyncio.sleep(0.02)
            await _read_sub_caches()  # what the handlers read after the lookup

    await asyncio.gather(*(sub_request() for _ in range(8)))

    assert reads == {"settings": 2, "secret_key": 1, "client_templates": 1, "xray_templates": 1}


async def test_refresh_while_requests_hold_connections_does_not_exhaust_pool(cold_caches, small_pool):
    session_factory, _, row = small_pool
    await _read_sub_caches()
    holding = asyncio.Semaphore(0)
    proceed = asyncio.Event()

    async def in_flight_request():
        async with session_factory() as db:
            await db.execute(text("SELECT 1"))
            holding.release()
            await proceed.wait()
            await _read_sub_caches()

    requests = [asyncio.create_task(in_flight_request()) for _ in range(2)]  # fill the whole pool
    for _ in requests:
        await holding.acquire()

    new_row = copy.deepcopy(row["settings"])
    new_row.hwid = {**new_row.hwid, "fallback_limit": 7}
    row["settings"] = new_row
    refresh = asyncio.create_task(refresh_caches())  # PUT /api/settings or the NATS message
    await asyncio.sleep(0.05)
    proceed.set()

    await asyncio.gather(*requests)
    await refresh
    assert (await hwid_settings()).fallback_limit == 7


async def test_load_started_before_refresh_does_not_store_stale_value(cold_caches, small_pool, monkeypatch):
    _, _, row = small_pool
    gate = asyncio.Event()
    started = asyncio.Event()
    calls = 0

    async def gated_get_settings(db):
        nonlocal calls
        calls += 1
        snapshot = row["settings"]
        if calls == 1:  # the read that began before the save: holds the old row
            started.set()
            await gate.wait()
        return snapshot

    monkeypatch.setattr("app.settings.get_settings", gated_get_settings)
    stale_read = asyncio.create_task(hwid_settings())
    await started.wait()

    new_row = copy.deepcopy(row["settings"])
    new_row.hwid = {**new_row.hwid, "fallback_limit": 9}
    row["settings"] = new_row
    await refresh_caches()
    gate.set()
    assert (await stale_read).fallback_limit == 3

    assert (await hwid_settings()).fallback_limit == 9


async def test_settings_save_releases_its_connection_before_reloading_caches(cold_caches, small_pool, monkeypatch):
    session_factory, reads, row = small_pool

    async def fake_modify_settings(db, _db_settings, _modify):
        await db.execute(text("SELECT 1"))  # db.refresh() after the commit opens a new transaction
        return row["settings"]

    async def published(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.operation.settings.get_settings", lambda db: _read_row(db, row))
    monkeypatch.setattr("app.operation.settings.modify_settings", fake_modify_settings)
    monkeypatch.setattr("app.operation.settings.router.publish", published)
    monkeypatch.setattr(SettingsOperation, "reset_services", staticmethod(published))

    async with session_factory() as other, session_factory() as db:
        await other.execute(text("SELECT 1"))  # another request holds the other pooled connection
        await SettingsOperation(OperatorType.API).modify_settings(db, SettingsSchema())

    assert reads["settings"] == 8  # every reload got a connection instead of timing out


async def _read_row(db, row):
    await db.execute(text("SELECT 1"))
    return row["settings"]


async def test_failed_template_read_is_not_cached_as_empty(cold_caches, monkeypatch):
    class UnavailableDB:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, _statement):
            raise PoolTimeoutError("QueuePool limit of size 1 overflow 0 reached")

    monkeypatch.setattr("app.subscription.client_templates.GetDB", UnavailableDB)

    await subscription_client_templates.refresh()

    with pytest.raises(PoolTimeoutError):  # retried, not served as an empty template map
        await subscription_client_templates()


async def test_cancelled_template_save_still_reloads_and_publishes(cold_caches, small_pool, monkeypatch):
    session_factory, reads, _ = small_pool
    started = asyncio.Event()
    gate = asyncio.Event()
    cleared = []
    published = []

    async def gated_client_template_values(db):
        started.set()
        await gate.wait()
        return {}

    async def publish(topic, message):
        published.append(topic)

    monkeypatch.setattr("app.subscription.client_templates.get_client_template_values", gated_client_template_values)
    monkeypatch.setattr("app.subscription.client_templates.clear_sub_config_cache", lambda: cleared.append(True))
    monkeypatch.setattr("app.operation.client_template.router.publish", publish)

    async with session_factory() as db:
        save = asyncio.create_task(ClientTemplateOperation._sync_client_template_cache(db))
        await started.wait()
        save.cancel()  # e.g. shutdown while the save waits for the first reload
        gate.set()
        with pytest.raises(asyncio.CancelledError):
            await save
        async with asyncio.timeout(1):
            while not published:
                await asyncio.sleep(0.01)

    assert reads["xray_templates"] == 1
    assert cleared == [True]
    assert len(published) == 1


def test_pool_exhaustion_returns_503(monkeypatch):
    async def exhausted(*args, **kwargs):
        raise PoolTimeoutError("QueuePool limit of size 5 overflow 5 reached")

    monkeypatch.setattr(subscription_router.subscription_operator, "user_subscription", exhausted)

    response = client.get("/sub/some-token/")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database temporarily unavailable"}
