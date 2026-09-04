from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.crud.user import _build_user_count_query_parts, _subscription_update_from_clause
from app.db.models import User, UserSubscriptionUpdate
from app.models.admin import AdminDetails, AdminRoleData
from app.models.stats import Period, UserCountMetric
from app.operation import OperatorType
from app.operation.user import UserOperation


@pytest_asyncio.fixture
async def statistics_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            user = User(username=f"statistics_{uuid4().hex[:8]}", admin_id=1)
            session.add(user)
            await session.flush()

            updates = [
                UserSubscriptionUpdate(user_id=user.id, user_agent="Clash", ip=None, hwid=None),
                UserSubscriptionUpdate(user_id=user.id, user_agent="Clash", ip=None, hwid=None),
                UserSubscriptionUpdate(user_id=user.id, user_agent="sing-box", ip=None, hwid=None),
            ]
            updates[0].created_at = datetime(2026, 8, 1, 12, tzinfo=UTC)
            updates[1].created_at = datetime(2026, 8, 2, 12, tzinfo=UTC)
            updates[2].created_at = datetime(2026, 8, 2, 13, tzinfo=UTC)
            session.add_all(updates)
            await session.commit()
            yield engine, session
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_subscription_chart_uses_one_history_select(statistics_session):
    engine, session = statistics_session
    history_selects = 0

    def count_history_selects(_, __, statement, *args):
        nonlocal history_selects
        if statement.lstrip().upper().startswith("SELECT") and "user_subscription_updates" in statement:
            history_selects += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_history_selects)
    try:
        result = await UserOperation(operator_type=OperatorType.API).get_users_sub_update_chart(
            session,
            admin=AdminDetails(username="owner", role=AdminRoleData(is_owner=True)),
            start=datetime(2026, 8, 1, tzinfo=UTC),
            end=datetime(2026, 8, 3, tzinfo=UTC),
            period=Period.day,
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_history_selects)

    assert history_selects == 1
    assert result.total == 3
    assert {(segment.name, segment.count) for segment in result.segments} == {("Clash", 2), ("sing-box", 1)}
    assert sum(stat.count for stat in result.stats) == 3


@pytest.mark.asyncio
async def test_history_queries_join_users_only_when_scope_requires_it(statistics_session):
    engine, session = statistics_session
    start = datetime(2026, 8, 1, tzinfo=UTC)
    end = datetime(2026, 8, 3, tzinfo=UTC)

    online_parts = _build_user_count_query_parts(
        session,
        admins=None,
        start=start,
        end=end,
        period=Period.day,
        metric=UserCountMetric.online,
        node_id=None,
    )
    online_sql = str(
        select(1).select_from(online_parts["from_clause"]).compile(dialect=engine.sync_engine.dialect)
    ).upper()

    expired_parts = _build_user_count_query_parts(
        session,
        admins=None,
        start=start,
        end=end,
        period=Period.day,
        metric=UserCountMetric.expired,
        node_id=None,
    )
    expired_sql = str(
        select(1).select_from(expired_parts["from_clause"]).compile(dialect=engine.sync_engine.dialect)
    ).upper()

    global_sub_from, _ = _subscription_update_from_clause()
    global_sub_sql = str(select(1).select_from(global_sub_from).compile(dialect=engine.sync_engine.dialect)).upper()
    scoped_sub_from, _ = _subscription_update_from_clause(admin_id=1)
    scoped_sub_sql = str(select(1).select_from(scoped_sub_from).compile(dialect=engine.sync_engine.dialect)).upper()

    assert "JOIN USERS" not in online_sql
    assert "JOIN USERS" in expired_sql
    assert "JOIN USERS" not in global_sub_sql
    assert "JOIN USERS" in scoped_sub_sql
