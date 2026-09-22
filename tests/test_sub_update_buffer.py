"""Buffered user_subscription_updates writes stay off the request commit path."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.crud.user import get_users_sub_update_list, user_sub_update
from app.db.models import User, UserSubscriptionUpdate
from app.subscription import sub_update_buffer


@pytest.fixture
async def buffer_db(monkeypatch: pytest.MonkeyPatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    class TestGetDB:
        def __init__(self):
            self.db = factory()

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, exc_type, exc_value, traceback):
            try:
                if exc_type is not None:
                    await self.db.rollback()
            finally:
                await self.db.close()

    monkeypatch.setattr(sub_update_buffer, "GetDB", TestGetDB)
    await sub_update_buffer.reset_user_sub_update_buffer()

    async with factory() as session:
        session.add(User(username="buffered"))
        await session.commit()
        user_id = (await session.execute(select(User.id).where(User.username == "buffered"))).scalar_one()
        yield session, user_id

    await sub_update_buffer.reset_user_sub_update_buffer()
    await engine.dispose()


@pytest.mark.asyncio
async def test_queue_does_not_write_until_flush(buffer_db):
    session, user_id = buffer_db
    await sub_update_buffer.queue_user_sub_update(user_id, "v2rayNG/1.0", ip="203.0.113.10", hwid="abc")

    count = (await session.execute(select(func.count()).select_from(UserSubscriptionUpdate))).scalar()
    assert count == 0
    assert sub_update_buffer.pending_count() == 1
    await session.commit()

    written = await sub_update_buffer.flush_user_sub_updates()
    assert written == 1
    assert sub_update_buffer.pending_count() == 0

    rows = (await session.execute(select(UserSubscriptionUpdate))).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_agent == "v2rayNG/1.0"
    assert rows[0].ip == "203.0.113.10"
    assert rows[0].hwid == "abc"


@pytest.mark.asyncio
async def test_user_sub_update_truncates_and_list_flushes(buffer_db):
    session, user_id = buffer_db
    await user_sub_update(session, user_id, "A" * 1000, ip="1.2.3.4")
    assert sub_update_buffer.pending_count() == 1

    stored, count = await get_users_sub_update_list(session, user_id)
    assert count == 1
    assert stored[0].user_agent == "A" * 512
    assert sub_update_buffer.pending_count() == 0


@pytest.mark.asyncio
async def test_flush_failure_requeues(buffer_db, monkeypatch: pytest.MonkeyPatch):
    _session, user_id = buffer_db
    await sub_update_buffer.queue_user_sub_update(user_id, "clash")

    class BoomGetDB:
        def __init__(self):
            raise SQLAlchemyError("boom")

    monkeypatch.setattr(sub_update_buffer, "GetDB", BoomGetDB)
    with pytest.raises(SQLAlchemyError):
        await sub_update_buffer.flush_user_sub_updates()
    assert sub_update_buffer.pending_count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("include_live_user", [False, True])
@pytest.mark.parametrize("batch_size", [1, 100])
async def test_flush_discards_deleted_users(buffer_db, monkeypatch, include_live_user, batch_size):
    session, user_id = buffer_db
    deleted_user = User(username="deleted_before_flush")
    session.add(deleted_user)
    await session.commit()
    await sub_update_buffer.queue_user_sub_update(deleted_user.id, "deleted-client")
    if include_live_user:
        await sub_update_buffer.queue_user_sub_update(user_id, "live-client")

    await session.execute(delete(User).where(User.id == deleted_user.id))
    await session.commit()
    monkeypatch.setattr(sub_update_buffer, "FLUSH_BATCH_SIZE", batch_size)

    assert await sub_update_buffer.flush_user_sub_updates() == int(include_live_user)
    assert sub_update_buffer.pending_count() == 0
    rows = (await session.execute(select(UserSubscriptionUpdate))).scalars().all()
    assert [(row.user_id, row.user_agent) for row in rows] == ([(user_id, "live-client")] if include_live_user else [])
    await session.commit()

    monkeypatch.setattr(sub_update_buffer, "FLUSH_BATCH_SIZE", 100)
    await sub_update_buffer.queue_user_sub_update(user_id, "next-client")
    assert await sub_update_buffer.flush_user_sub_updates() == 1
    assert sub_update_buffer.pending_count() == 0


@pytest.mark.asyncio
async def test_second_flush_waits_until_in_flight_drain_commits(buffer_db, monkeypatch):
    session, user_id = buffer_db
    inner_cls = sub_update_buffer.GetDB
    first_entered = asyncio.Event()
    release = asyncio.Event()
    calls = {"n": 0}

    class WrappedGetDB:
        def __init__(self):
            self._inner = inner_cls()

        async def __aenter__(self):
            calls["n"] += 1
            if calls["n"] == 1:
                first_entered.set()
                await release.wait()
            return await self._inner.__aenter__()

        async def __aexit__(self, exc_type, exc_value, traceback):
            return await self._inner.__aexit__(exc_type, exc_value, traceback)

    monkeypatch.setattr(sub_update_buffer, "GetDB", WrappedGetDB)
    await sub_update_buffer.queue_user_sub_update(user_id, "first-client")
    first_flush = asyncio.create_task(sub_update_buffer.flush_user_sub_updates())
    await first_entered.wait()
    await sub_update_buffer.queue_user_sub_update(user_id, "second-client")
    second_flush = asyncio.create_task(sub_update_buffer.flush_user_sub_updates())
    await asyncio.sleep(0.05)
    assert not second_flush.done()
    release.set()
    written = await first_flush + await second_flush
    assert written == 2
    assert second_flush.done()
    assert sub_update_buffer.pending_count() == 0
    rows = (await session.execute(select(UserSubscriptionUpdate))).scalars().all()
    assert sorted(row.user_agent for row in rows) == ["first-client", "second-client"]
    await session.commit()


@pytest.mark.asyncio
async def test_queue_spawns_flush_only_when_crossing_batch_size(buffer_db, monkeypatch):
    _session, user_id = buffer_db
    created: list[str | None] = []
    real_create_task = asyncio.create_task

    def tracking_create_task(coro, *args, **kwargs):
        created.append(kwargs.get("name"))
        coro.close()
        return real_create_task(asyncio.sleep(0), name=kwargs.get("name"))

    monkeypatch.setattr(sub_update_buffer.asyncio, "create_task", tracking_create_task)
    monkeypatch.setattr(sub_update_buffer, "FLUSH_BATCH_SIZE", 2)

    await sub_update_buffer.queue_user_sub_update(user_id, "one")
    assert created == []
    await sub_update_buffer.queue_user_sub_update(user_id, "two")
    assert created == ["sub_update_flush"]
    await sub_update_buffer.queue_user_sub_update(user_id, "three")
    assert created == ["sub_update_flush"]
    await sub_update_buffer.reset_user_sub_update_buffer()
    assert sub_update_buffer.pending_count() == 0
