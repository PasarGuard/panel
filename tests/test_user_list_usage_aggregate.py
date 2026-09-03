"""Regression tests for scalable user-list lifetime usage loading."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.crud.user import get_users
from app.db.models import User, UserStatus, UserUsageResetLogs
from app.models.admin import AdminDetails
from app.models.user import UserListQuery
from app.operation import OperatorType
from app.operation.user import UserOperation


@pytest_asyncio.fixture
async def seeded_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            users = [
                User(username="aggregate-user-with-history", used_traffic=7, status=UserStatus.active),
                User(username="aggregate-user-without-history", used_traffic=11, status=UserStatus.active),
            ]
            session.add_all(users)
            await session.flush()
            session.add_all(
                [
                    UserUsageResetLogs(user_id=users[0].id, used_traffic_at_reset=13),
                    UserUsageResetLogs(user_id=users[0].id, used_traffic_at_reset=17),
                ]
            )
            await session.commit()

        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_users_aggregates_lifetime_usage_without_loading_history(seeded_session):
    users, total = await get_users(
        seeded_session,
        UserListQuery(sort=["username"]),
        return_with_count=True,
        load_usage_logs=False,
        load_lifetime_used_traffic=True,
    )

    assert total == 2
    assert [user.lifetime_used_traffic for user in users] == [37, 11]
    assert all("usage_logs" in sa_inspect(user).unloaded for user in users)


@pytest.mark.asyncio
async def test_panel_user_list_requests_aggregate_instead_of_history(monkeypatch):
    load_users = AsyncMock(return_value=([], 0))
    monkeypatch.setattr("app.operation.user.get_users", load_users)
    operator = UserOperation(OperatorType.WEB)

    response = await operator.get_users(object(), AdminDetails(username="owner"), UserListQuery())

    assert response.total == 0
    assert load_users.await_args.kwargs["load_usage_logs"] is False
    assert load_users.await_args.kwargs["load_lifetime_used_traffic"] is True
