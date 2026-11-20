import asyncio

import pytest
from fastapi import status
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import APIKey
from app.operation import api_key_usage_buffer
from app.routers.authentication import get_admin_from_api_key
from tests.api import DATABASE_URL, IS_SQLITE, TestSession, client, engine
from tests.api.helpers import auth_headers, create_admin, delete_admin, unique_name


@pytest.fixture(autouse=True)
def empty_usage_buffer(monkeypatch):
    api_key_usage_buffer.reset_api_key_usage_buffer()
    # Each test runs its own event loop; a lock that was waited on stays bound to the old one.
    monkeypatch.setattr(api_key_usage_buffer, "_drain_lock", asyncio.Lock())
    yield
    api_key_usage_buffer.reset_api_key_usage_buffer()


@pytest.fixture
def key_owner(access_token):
    admin = create_admin(access_token, role_id=2)
    response = client.post(
        "/api/admin/token",
        data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    yield admin, response.json()["access_token"]
    delete_admin(access_token, admin["username"])


def _create_key(admin_token: str, **fields) -> dict:
    response = client.post(
        "/api/api_key",
        headers=auth_headers(admin_token),
        json={"name": unique_name("api_key"), "role_id": 2, **fields},
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def _stored_count(key_id: int) -> int | None:
    async def _get() -> int | None:
        async with TestSession() as session:
            return await session.scalar(select(APIKey.request_count).where(APIKey.id == key_id))

    return asyncio.run(_get())


def _stored_hash(key_id: int) -> str:
    async def _get() -> str:
        async with TestSession() as session:
            return await session.scalar(select(APIKey.key_hash).where(APIKey.id == key_id))

    return asyncio.run(_get())


def _set_limit_directly(key_id: int, max_requests: int) -> None:
    """Change the limit the way another process would: no flush of this process's buffer."""

    async def _set() -> None:
        async with TestSession() as session:
            await session.execute(update(APIKey).where(APIKey.id == key_id).values(max_requests=max_requests))
            await session.commit()

    asyncio.run(_set())


def _authenticate(raw_key: str) -> int:
    return client.get("/api/admin", headers={"X-Api-Key": raw_key}).status_code


class _ApiKeyUpdateCounter:
    def __init__(self):
        self.count = 0

    def __call__(self, conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE API_KEYS"):
            self.count += 1

    def __enter__(self):
        event.listen(engine.sync_engine, "before_cursor_execute", self)
        return self

    def __exit__(self, *exc):
        event.remove(engine.sync_engine, "before_cursor_execute", self)


def test_unlimited_key_requests_do_not_update_the_row_until_flush(key_owner):
    _, admin_token = key_owner
    created = _create_key(admin_token)

    with _ApiKeyUpdateCounter() as updates:
        for _ in range(5):
            assert _authenticate(created["api_key"]) == status.HTTP_200_OK

    assert updates.count == 0
    assert api_key_usage_buffer.pending_api_key_usage(created["id"]) == 5
    assert _stored_count(created["id"]) == 0

    assert asyncio.run(api_key_usage_buffer.flush_api_key_usage()) == 5
    assert _stored_count(created["id"]) == 5
    assert api_key_usage_buffer.pending_api_key_usage(created["id"]) == 0


def test_limited_key_still_updates_the_row_on_every_request(key_owner):
    _, admin_token = key_owner
    created = _create_key(admin_token, max_requests=10)

    with _ApiKeyUpdateCounter() as updates:
        for _ in range(3):
            assert _authenticate(created["api_key"]) == status.HTTP_200_OK

    assert updates.count == 3
    assert api_key_usage_buffer.pending_api_key_usage(created["id"]) == 0
    assert _stored_count(created["id"]) == 3


def test_limited_key_admits_exactly_max_requests_under_concurrency(key_owner):
    _, admin_token = key_owner
    created = _create_key(admin_token, max_requests=5)

    async def _run() -> list[bool]:
        if IS_SQLITE:
            # Separate connections, so the requests really compete for the row.
            parallel_engine = create_async_engine(DATABASE_URL, poolclass=NullPool, connect_args={"timeout": 30})
        else:
            parallel_engine = engine
        sessions = async_sessionmaker(parallel_engine, expire_on_commit=False, autoflush=False)

        async def _one() -> bool:
            async with sessions() as db:
                return await get_admin_from_api_key(db, created["api_key"]) is not None

        try:
            return await asyncio.gather(*(_one() for _ in range(20)))
        finally:
            if parallel_engine is not engine:
                await parallel_engine.dispose()

    results = asyncio.run(_run())

    assert sum(results) == 5
    assert _stored_count(created["id"]) == 5
    assert _authenticate(created["api_key"]) == status.HTTP_401_UNAUTHORIZED


def test_limit_set_through_api_counts_buffered_requests(key_owner):
    _, admin_token = key_owner
    created = _create_key(admin_token)
    for _ in range(3):
        assert _authenticate(created["api_key"]) == status.HTTP_200_OK

    response = client.patch(
        f"/api/api_key/{created['id']}", headers=auth_headers(admin_token), json={"max_requests": 5}
    )
    assert response.status_code == status.HTTP_200_OK
    assert _stored_count(created["id"]) == 3

    assert _authenticate(created["api_key"]) == status.HTTP_200_OK
    assert _authenticate(created["api_key"]) == status.HTTP_200_OK
    assert _authenticate(created["api_key"]) == status.HTTP_401_UNAUTHORIZED
    assert _stored_count(created["id"]) == 5


def test_limit_set_elsewhere_counts_buffered_requests_on_next_request(key_owner):
    _, admin_token = key_owner
    created = _create_key(admin_token)
    for _ in range(3):
        assert _authenticate(created["api_key"]) == status.HTTP_200_OK
    _set_limit_directly(created["id"], 5)

    assert _authenticate(created["api_key"]) == status.HTTP_200_OK
    assert _stored_count(created["id"]) == 4
    assert api_key_usage_buffer.pending_api_key_usage(created["id"]) == 0
    assert _authenticate(created["api_key"]) == status.HTTP_200_OK
    assert _authenticate(created["api_key"]) == status.HTTP_401_UNAUTHORIZED
    assert _stored_count(created["id"]) == 5


def test_buffered_requests_beyond_a_new_limit_are_kept_and_block_the_key(key_owner):
    _, admin_token = key_owner
    created = _create_key(admin_token)
    for _ in range(3):
        assert _authenticate(created["api_key"]) == status.HTTP_200_OK
    _set_limit_directly(created["id"], 2)

    assert _authenticate(created["api_key"]) == status.HTTP_401_UNAUTHORIZED
    assert _stored_count(created["id"]) == 3
    assert api_key_usage_buffer.pending_api_key_usage(created["id"]) == 0


def test_revoke_resets_counter_despite_buffered_requests(key_owner):
    _, admin_token = key_owner
    created = _create_key(admin_token)
    for _ in range(3):
        assert _authenticate(created["api_key"]) == status.HTTP_200_OK

    response = client.post(f"/api/api_key/{created['id']}/revoke", headers=auth_headers(admin_token))
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["request_count"] == 0

    asyncio.run(api_key_usage_buffer.flush_api_key_usage())
    assert _stored_count(created["id"]) == 0


def test_flush_skips_deleted_key(key_owner):
    _, admin_token = key_owner
    deleted = _create_key(admin_token)
    kept = _create_key(admin_token)
    assert _authenticate(deleted["api_key"]) == status.HTTP_200_OK
    assert _authenticate(kept["api_key"]) == status.HTTP_200_OK

    response = client.delete(f"/api/api_key/{deleted['id']}", headers=auth_headers(admin_token))
    assert response.status_code == status.HTTP_204_NO_CONTENT

    asyncio.run(api_key_usage_buffer.flush_api_key_usage())
    assert _stored_count(deleted["id"]) is None
    assert _stored_count(kept["id"]) == 1
    assert api_key_usage_buffer.pending_api_key_usage(deleted["id"]) == 0


def test_requests_of_a_replaced_key_do_not_reach_a_key_with_the_same_id(key_owner):
    # SQLite can hand a deleted key's id to the next key; the old key's requests must not move over.
    _, admin_token = key_owner
    created = _create_key(admin_token)
    api_key_usage_buffer.record_api_key_usage(created["id"], "v1$old$sha256$deadbeef")

    assert _authenticate(created["api_key"]) == status.HTTP_200_OK
    asyncio.run(api_key_usage_buffer.flush_api_key_usage())
    assert _stored_count(created["id"]) == 1

    _set_limit_directly(created["id"], 10)
    api_key_usage_buffer.record_api_key_usage(created["id"], "v1$old$sha256$deadbeef")
    assert _authenticate(created["api_key"]) == status.HTTP_200_OK
    assert _stored_count(created["id"]) == 2


def test_shutdown_flushes_buffer_and_stops_loop(key_owner, monkeypatch):
    _, admin_token = key_owner
    created = _create_key(admin_token)
    key_hash = _stored_hash(created["id"])
    monkeypatch.setattr(api_key_usage_buffer, "FLUSH_INTERVAL_SECONDS", 3600)

    async def _lifecycle() -> None:
        await api_key_usage_buffer.start_api_key_usage_flusher()
        task = api_key_usage_buffer._flush_task
        assert task is not None and not task.done()
        for _ in range(4):
            api_key_usage_buffer.record_api_key_usage(created["id"], key_hash)
        await api_key_usage_buffer.stop_api_key_usage_flusher()
        assert task.cancelled()
        assert api_key_usage_buffer._flush_task is None

    asyncio.run(_lifecycle())
    assert _stored_count(created["id"]) == 4
    assert api_key_usage_buffer.pending_api_key_usage(created["id"]) == 0


def test_failed_flush_keeps_requests_for_next_attempt(key_owner, monkeypatch):
    _, admin_token = key_owner
    created = _create_key(admin_token)
    key_hash = _stored_hash(created["id"])
    api_key_usage_buffer.record_api_key_usage(created["id"], key_hash)
    api_key_usage_buffer.record_api_key_usage(created["id"], key_hash)

    class _BrokenDB:
        async def __aenter__(self):
            raise RuntimeError("database unavailable")

        async def __aexit__(self, *exc):
            return False

    with monkeypatch.context() as patch:
        patch.setattr(api_key_usage_buffer, "GetDB", _BrokenDB)
        with pytest.raises(RuntimeError):
            asyncio.run(api_key_usage_buffer.flush_api_key_usage())
    assert api_key_usage_buffer.pending_api_key_usage(created["id"]) == 2

    asyncio.run(api_key_usage_buffer.flush_api_key_usage())
    assert _stored_count(created["id"]) == 2


def test_shutdown_during_a_periodic_flush_does_not_drop_its_batch(key_owner, monkeypatch):
    _, admin_token = key_owner
    created = _create_key(admin_token)
    key_hash = _stored_hash(created["id"])
    monkeypatch.setattr(api_key_usage_buffer, "FLUSH_INTERVAL_SECONDS", 0.01)
    real_get_db = api_key_usage_buffer.GetDB

    async def _lifecycle() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        class _SlowDB:
            def __init__(self):
                self._inner = real_get_db()

            async def __aenter__(self):
                entered.set()
                await release.wait()
                return await self._inner.__aenter__()

            async def __aexit__(self, *exc):
                return await self._inner.__aexit__(*exc)

        monkeypatch.setattr(api_key_usage_buffer, "GetDB", _SlowDB)
        for _ in range(3):
            api_key_usage_buffer.record_api_key_usage(created["id"], key_hash)
        await api_key_usage_buffer.start_api_key_usage_flusher()
        await asyncio.wait_for(entered.wait(), 5)
        asyncio.get_running_loop().call_later(0.05, release.set)
        await api_key_usage_buffer.stop_api_key_usage_flusher()

    asyncio.run(_lifecycle())
    assert _stored_count(created["id"]) == 3
    assert api_key_usage_buffer.pending_api_key_usage(created["id"]) == 0


def test_modify_key_survives_a_failed_usage_flush(key_owner, monkeypatch):
    _, admin_token = key_owner
    created = _create_key(admin_token)
    key_hash = _stored_hash(created["id"])
    api_key_usage_buffer.record_api_key_usage(created["id"], key_hash)

    class _BrokenDB:
        async def __aenter__(self):
            raise RuntimeError("database unavailable")

        async def __aexit__(self, *exc):
            return False

    with monkeypatch.context() as patch:
        patch.setattr(api_key_usage_buffer, "GetDB", _BrokenDB)
        response = client.patch(
            f"/api/api_key/{created['id']}", headers=auth_headers(admin_token), json={"max_requests": 5}
        )
    assert response.status_code == status.HTTP_200_OK
    assert api_key_usage_buffer.pending_api_key_usage(created["id"]) == 1

    assert _authenticate(created["api_key"]) == status.HTTP_200_OK
    assert _stored_count(created["id"]) == 2
