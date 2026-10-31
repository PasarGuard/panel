"""The expired reminder cleanup job must persist its delete."""

from datetime import UTC, datetime as dt, timedelta as td

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.models import NotificationReminder, ReminderType, User, UserStatus
from app.jobs.send_notifications import delete_expired_reminders


@pytest.fixture
async def session_factory(monkeypatch: pytest.MonkeyPatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    # GetDB opens its sessions from base.SessionLocal and never commits on its own.
    monkeypatch.setattr(base, "SessionLocal", factory)
    yield factory
    await engine.dispose()


async def test_delete_expired_reminders_commits_the_delete(session_factory):
    now = dt.now(UTC).replace(tzinfo=None)
    async with session_factory() as db:
        user = User(username="reminded", status=UserStatus.active)
        db.add(user)
        await db.flush()
        db.add_all(
            [
                NotificationReminder(
                    user_id=user.id, type=ReminderType.data_usage, threshold=80, expires_at=now - td(days=1)
                ),
                NotificationReminder(
                    user_id=user.id, type=ReminderType.expiration_date, threshold=3, expires_at=now + td(days=1)
                ),
            ]
        )
        await db.commit()

    await delete_expired_reminders()

    async with session_factory() as db:
        remaining = (await db.execute(select(NotificationReminder.type))).scalars().all()
    assert remaining == [ReminderType.expiration_date]
