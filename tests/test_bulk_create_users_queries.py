"""Bulk user creation loads the new users' relations in a fixed number of statements, not a few per user, and hands
the same values to the response, the node sync and the notification as a fresh load of those users. Runs on SQLite by
default and on PostgreSQL/MySQL/MariaDB with TEST_FROM=github."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, insert, select

import app.operation.user as user_operation_module
from app.db.crud.admin import get_admin
from app.db.crud.user import get_users_by_usernames
from app.db.models import Admin, Group, ProxyInbound, UserTemplate, template_group_association
from app.models.admin import AdminDetails, AdminRoleData
from app.models.user import (
    BulkUsersFromTemplate,
    NextPlanModel,
    UserCreate,
    UsernameGenerationStrategy,
)
from app.operation import OperatorType
from app.operation.user import UserOperation
from tests.test_record_usages import reset_user_usage_history_buffer, session_factory  # noqa: F401

ADMIN = "bulk-create-admin"


async def _fake_subscription_url(user) -> str:
    # The real one reads the settings row through the app's own session; the admin part shows it is loaded
    return f"sub/{user.id}/{user.admin.username if user.admin else ''}"


@pytest.fixture
def operation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(UserOperation, "generate_subscription_url", staticmethod(_fake_subscription_url))
    monkeypatch.setattr(user_operation_module, "sync_users", AsyncMock())
    monkeypatch.setattr(user_operation_module.notification, "bulk_create_users", AsyncMock())
    return UserOperation(OperatorType.API)


async def _seed(session_factory, prefix: str) -> int:  # noqa: F811
    async with session_factory() as db:
        inbound = ProxyInbound(tag=f"{prefix}-vless")
        db.add_all([Admin(username=ADMIN, hashed_password="x", role_id=1), inbound])
        await db.flush()
        group = Group(name=f"{prefix}-group", inbounds=[inbound])
        template = UserTemplate(
            name=f"{prefix}-template",
            username_prefix=None,
            username_suffix=None,
            extra_settings=None,
            groups=[],
            data_limit=1024,
            expire_duration=86400,
        )
        db.add_all([group, template])
        await db.flush()
        await db.execute(insert(template_group_association), [{"user_template_id": template.id, "group_id": group.id}])
        await db.commit()
        return template.id


@contextmanager
def _statements_after_insert(db):
    """Record the statements `_persist_bulk_users` runs after `create_users_bulk` has inserted the batch."""
    statements: list[str] = []
    recording = False
    original_create = user_operation_module.create_users_bulk

    async def create_users_bulk(*args, **kwargs):
        nonlocal recording
        users = await original_create(*args, **kwargs)
        recording = True
        return users

    def count(_conn, _cursor, statement, *_args):
        if recording:
            statements.append(statement)

    original_persist = UserOperation._persist_bulk_users

    async def persist(self, *args, **kwargs):
        nonlocal recording
        try:
            return await original_persist(self, *args, **kwargs)
        finally:
            recording = False

    user_operation_module.create_users_bulk = create_users_bulk
    UserOperation._persist_bulk_users = persist
    event.listen(db.bind.sync_engine, "before_cursor_execute", count)
    try:
        yield statements
    finally:
        event.remove(db.bind.sync_engine, "before_cursor_execute", count)
        user_operation_module.create_users_bulk = original_create
        UserOperation._persist_bulk_users = original_persist


def _owner() -> AdminDetails:
    return AdminDetails(username=ADMIN, role=AdminRoleData(is_owner=True))


async def _fresh_responses(session_factory, operation, usernames: list[str]) -> list[dict]:  # noqa: F811
    async with session_factory() as db:
        users = await get_users_by_usernames(db, usernames, load_admin_role=True)
        return [(await operation.validate_user(user)).model_dump() for user in users]


@pytest.mark.asyncio
async def test_bulk_create_from_template_loads_new_users_in_fixed_statements(session_factory, operation):  # noqa: F811
    template_id = await _seed(session_factory, "tpl")

    async def create(count: int, base: str) -> int:
        async with session_factory() as db:
            body = BulkUsersFromTemplate(
                user_template_id=template_id,
                username=base,
                strategy=UsernameGenerationStrategy.sequence,
                count=count,
                start_number=1,
            )
            with _statements_after_insert(db) as statements:
                response = await operation.bulk_create_users_from_template(db, body, _owner())

        usernames = [f"{base}{index}" for index in range(1, count + 1)]
        expected = await _fresh_responses(session_factory, operation, usernames)
        notified = user_operation_module.notification.bulk_create_users.call_args.args[0]
        synced = user_operation_module.sync_users.call_args.args[0]

        assert response.created == count
        assert response.subscription_urls == [user["subscription_url"] for user in expected]
        assert [user.model_dump() for user in notified] == expected
        assert [user.username for user in synced] == usernames
        assert {user.lifetime_used_traffic for user in synced} == {0}
        assert {user["admin"]["username"] for user in expected} == {ADMIN}
        assert {tuple(user["group_names"]) for user in expected} == {("tpl-group",)}
        assert {user["next_plan"] for user in expected} == {None}
        return len(statements)

    few = await create(3, "few")
    many = await create(12, "many")
    assert many == few, f"{few} statements after the insert for 3 users, {many} for 12"


@pytest.mark.asyncio
async def test_persist_bulk_users_with_next_plan_matches_fresh_load(session_factory, operation):  # noqa: F811
    template_id = await _seed(session_factory, "np")

    async def persist(count: int, base: str) -> int:
        async with session_factory() as db:
            group_id = (await db.execute(select(Group.id).where(Group.name == "np-group"))).scalar_one()
            users_to_create = [
                UserCreate(
                    username=f"{base}{index}",
                    group_ids=[group_id],
                    data_limit=2048,
                    # Every other user gets a next plan, the rest none
                    next_plan=(
                        NextPlanModel(user_template_id=template_id, data_limit=4096, expire=3600) if index % 2 else None
                    ),
                )
                for index in range(count)
            ]
            groups = await operation.validate_all_groups(db, users_to_create[0], _owner())
            db_admin = await get_admin(db, ADMIN, load_users=False, load_usage_logs=False)
            with _statements_after_insert(db) as statements:
                urls = await operation._persist_bulk_users(
                    db, _owner(), db_admin, users_to_create, groups, skip_per_user_limits=True, commit=False, sync=False
                )
            await db.commit()
            in_session = [
                (await operation.validate_user(user)).model_dump()
                for user in await operation._load_users_by_usernames(db, [user.username for user in users_to_create])
            ]

        expected = await _fresh_responses(session_factory, operation, [user.username for user in users_to_create])
        assert in_session == expected
        assert urls == [user["subscription_url"] for user in expected]
        assert [user["next_plan"] is not None for user in expected] == [bool(index % 2) for index in range(count)]
        assert {user["next_plan"]["data_limit"] for user in expected if user["next_plan"]} == {4096}
        return len(statements)

    few = await persist(3, "np-few")
    many = await persist(12, "np-many")
    assert many == few, f"{few} statements after the insert for 3 users, {many} for 12"
