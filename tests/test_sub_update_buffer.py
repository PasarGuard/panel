"""Buffered user_subscription_updates writes stay off the request commit path."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
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
