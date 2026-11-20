"""Bulk subscription revoke and expired-user auto-delete reload their users in a fixed number of statements, not a
few statements per user. Runs on SQLite by default and on PostgreSQL/MySQL/MariaDB with TEST_FROM=github."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select

from app.db.crud.user import autodelete_expired_users, bulk_revoke_user_sub, get_user_by_id
from app.db.models import Admin, Group, NextPlan, ProxyInbound, User, UserStatus, UserUsageResetLogs
from app.models.proxy import ProxyTable
from app.models.user import UserNotificationResponse
from tests.test_record_usages import reset_user_usage_history_buffer, session_factory  # noqa: F401


@contextmanager
def _count_statements(db):
    statements: list[str] = []
    sync_engine = db.bind.sync_engine

    def count(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(sync_engine, "before_cursor_execute", count)
    try:
        yield statements
    finally:
        event.remove(sync_engine, "before_cursor_execute", count)


async def _seed_users(db, count: int, prefix: str, **user_kwargs) -> list[int]:
    admin = Admin(username=f"{prefix}-admin", hashed_password="x", role_id=3)
    group = Group(name=f"{prefix}-group", inbounds=[ProxyInbound(tag=f"{prefix}-inbound")])
    db.add_all([admin, group])
    await db.flush()
    users = [
        User(
            username=f"{prefix}{index}",
            proxy_settings=ProxyTable().dict(no_obj=True),
            admin_id=admin.id,
            used_traffic=10,
            **user_kwargs,
        )
        for index in range(count)
    ]
    db.add_all(users)
    await db.flush()
    for user in users:
        await user.awaitable_attrs.groups
        user.groups.append(group)
        db.add(NextPlan(user_id=user.id, user_template_id=None, data_limit=100))
        db.add(UserUsageResetLogs(user_id=user.id, used_traffic_at_reset=1))
    await db.commit()
    return [user.id for user in users]


@pytest.mark.asyncio
async def test_bulk_revoke_statement_count_does_not_grow_with_users(session_factory):  # noqa: F811
    async def statements_for(count: int, prefix: str) -> int:
        async with session_factory() as db:
            user_ids = await _seed_users(db, count, prefix)

        async with session_factory() as db:
            # Reverse the id order: the result must keep the caller's order, not the database's
            requested_ids = list(reversed(user_ids))
            users = [await get_user_by_id(db, user_id, load_usage_logs=False) for user_id in requested_ids]
            with _count_statements(db) as statements:
                revoked = await bulk_revoke_user_sub(db, users)
                # Everything the caller reads afterwards (node sync, notifications, response) is already loaded
                inbounds = [await user.inbounds() for user in revoked]
                responses = [UserNotificationResponse.model_validate(user) for user in revoked]
                admin_roles = [user.admin.role.name for user in revoked]

            assert [user.id for user in revoked] == requested_ids
            assert all(user.sub_revoked_at is not None for user in revoked)
            assert inbounds == [[f"{prefix}-inbound"]] * count
            assert {user.lifetime_used_traffic for user in revoked} == {11}
            assert [response.group_names for response in responses] == [[f"{prefix}-group"]] * count
            assert {response.next_plan.data_limit for response in responses} == {100}
            assert set(admin_roles) == {"operator"}
        return len(statements)

    few = await statements_for(5, "few")
    many = await statements_for(20, "many")
    assert many == few, f"{few} statements for 5 users, {many} for 20"


@pytest.mark.asyncio
async def test_autodelete_statement_count_does_not_grow_with_users(session_factory):  # noqa: F811
    async def statements_for(count: int, prefix: str) -> int:
        async with session_factory() as db:
            await _seed_users(
                db,
                count,
                prefix,
                status=UserStatus.expired,
                last_status_change=datetime.now(UTC) - timedelta(days=3),
            )

        async with session_factory() as db:
            with _count_statements(db) as statements:
                deleted = await autodelete_expired_users(db, default_autodelete_days=1)
            assert await db.scalar(select(func.count()).select_from(User)) == 0

        assert sorted(user.username for user in deleted) == sorted(f"{prefix}{index}" for index in range(count))
        assert {user.lifetime_used_traffic for user in deleted} == {11}
        assert [user.group_names for user in deleted] == [[f"{prefix}-group"]] * count
        assert {user.next_plan.data_limit for user in deleted} == {100}
        assert {user.admin.username for user in deleted} == {f"{prefix}-admin"}
        return len(statements)

    few = await statements_for(5, "few")
    many = await statements_for(20, "many")
    assert many == few, f"{few} statements for 5 users, {many} for 20"
