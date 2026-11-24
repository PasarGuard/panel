from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.crud.user import remove_user, remove_users
from app.db.models import NodeUserUsage, User, UserSubscriptionUpdate, UserUsageResetLogs


@pytest.fixture
async def sqlite_db():
    """SQLite without foreign key enforcement, like the panel's own connections."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


async def _user_with_history(db, username: str) -> User:
    user = User(username=username, proxy_settings={})
    db.add(user)
    await db.flush()
    db.add_all(
        [
            UserUsageResetLogs(user_id=user.id, used_traffic_at_reset=1024),
            NodeUserUsage(created_at=datetime(2026, 1, 1, tzinfo=UTC), user_id=user.id, node_id=None, used_traffic=10),
            UserSubscriptionUpdate(user_id=user.id, user_agent="client/1.0"),
        ]
    )
    await db.commit()
    return user


async def _dependent_rows(db, user_id: int) -> int:
    total = 0
    for model in (UserUsageResetLogs, NodeUserUsage, UserSubscriptionUpdate):
        total += await db.scalar(select(func.count()).select_from(model).where(model.user_id == user_id))
    return total


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_deleting_a_user_removes_its_rows(sqlite_db, bulk):
    """A new user that reuses a deleted user's id must not inherit its history (SQLite reuses the highest id)."""
    user = await _user_with_history(sqlite_db, "delete-dependencies")
    user_id = user.id

    if bulk:
        await remove_users(sqlite_db, [user])
    else:
        await remove_user(sqlite_db, user)

    assert await _dependent_rows(sqlite_db, user_id) == 0

    reused = User(username="delete-dependencies-new", proxy_settings={})
    sqlite_db.add(reused)
    await sqlite_db.commit()
    assert reused.id == user_id
    assert await _dependent_rows(sqlite_db, reused.id) == 0
