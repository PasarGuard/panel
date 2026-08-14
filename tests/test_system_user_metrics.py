from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.crud.user import _build_user_count_metrics_query, get_users_count_metrics
from app.db.models import User, UserStatus

STATUSES = [
    UserStatus.active,
    UserStatus.disabled,
    UserStatus.on_hold,
    UserStatus.expired,
    UserStatus.limited,
]


@pytest.mark.asyncio
async def test_user_count_metrics_are_scoped_complete_and_use_one_select():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    prefix = uuid4().hex[:8]

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add_all(
                [
                    User(
                        username=f"{prefix}_active",
                        admin_id=101,
                        status=UserStatus.active,
                        online_at=now - timedelta(seconds=30),
                    ),
                    User(
                        username=f"{prefix}_disabled",
                        admin_id=101,
                        status=UserStatus.disabled,
                    ),
                    User(
                        username=f"{prefix}_expired",
                        admin_id=101,
                        status=UserStatus.expired,
                        online_at=now - timedelta(minutes=3),
                    ),
                    User(
                        username=f"{prefix}_limited",
                        admin_id=202,
                        status=UserStatus.limited,
                        online_at=now - timedelta(seconds=45),
                    ),
                    User(
                        username=f"{prefix}_on_hold",
                        admin_id=202,
                        status=UserStatus.on_hold,
                    ),
                ]
            )
            await session.flush()

            select_count = 0

            def count_selects(_, __, statement, *args):
                nonlocal select_count
                if statement.lstrip().upper().startswith("SELECT"):
                    select_count += 1

            event.listen(engine.sync_engine, "before_cursor_execute", count_selects)
            try:
                global_counts, global_online = await get_users_count_metrics(session, STATUSES, timedelta(minutes=2))
            finally:
                event.remove(engine.sync_engine, "before_cursor_execute", count_selects)

            assert select_count == 1
            assert global_counts == {
                "active": 1,
                "disabled": 1,
                "on_hold": 1,
                "expired": 1,
                "limited": 1,
                "total": 5,
            }
            assert global_online == 2

            scoped_counts, scoped_online = await get_users_count_metrics(
                session, STATUSES, timedelta(minutes=2), admin_id=101
            )
            assert scoped_counts == {
                "active": 1,
                "disabled": 1,
                "on_hold": 0,
                "expired": 1,
                "limited": 0,
                "total": 3,
            }
            assert scoped_online == 1

            empty_counts, empty_online = await get_users_count_metrics(
                session, STATUSES, timedelta(minutes=2), admin_id=999
            )
            assert empty_counts == {
                "active": 0,
                "disabled": 0,
                "on_hold": 0,
                "expired": 0,
                "limited": 0,
                "total": 0,
            }
            assert empty_online == 0
    finally:
        await engine.dispose()


@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect(), mysql.dialect()])
def test_global_user_count_metrics_query_compiles_for_supported_dialects(dialect):
    stmt = _build_user_count_metrics_query(STATUSES, datetime(2026, 1, 1, tzinfo=UTC))

    sql = str(stmt.compile(dialect=dialect)).upper()

    assert sql.startswith("SELECT")
    assert "COUNT(CASE WHEN" in sql
    assert sql.count("FROM USERS") == 1


@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect(), mysql.dialect()])
def test_scoped_user_count_metrics_query_compiles_to_indexable_counts(dialect):
    stmt = _build_user_count_metrics_query(STATUSES, datetime(2026, 1, 1, tzinfo=UTC), admin_id=1)

    sql = str(stmt.compile(dialect=dialect)).upper()

    assert sql.startswith("SELECT")
    assert "COUNT(CASE WHEN" not in sql
    assert sql.count("SELECT COUNT(") == len(STATUSES) + 1
    assert sql.count("USERS.ADMIN_ID =") == len(STATUSES) + 1
