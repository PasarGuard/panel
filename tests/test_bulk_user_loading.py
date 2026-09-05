from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.db import Base
from app.db.crud import bulk
from app.db.models import Admin, AdminRole, Group, NextPlan, User, UserStatus, UserUsageResetLogs
from app.models.group import BulkGroup
from app.models.user import BulkUser, BulkUsersProxy, UserResponse


@pytest.fixture
async def bulk_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db:
        role = AdminRole(name="bulk-role")
        db.add(role)
        await db.flush()
        admin = Admin(username="bulk-admin", hashed_password="test", role_id=role.id)
        group = Group(name="bulk-group", inbounds=[])
        other_group = Group(name="other-group", inbounds=[])
        db.add_all([admin, group, other_group])
        await db.flush()
        for i in range(1, 5):
            user = User(
                username=f"bulk-user-{i}",
                admin_id=admin.id,
                used_traffic=100,
                data_limit=100,
                status=UserStatus.limited if i < 3 else UserStatus.disabled,
                proxy_settings={"shadowsocks": {"password": "x" * 32, "method": "aes-128-gcm"}},
            )
            user.expire = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
            user.groups = [other_group] if i < 3 else [group, other_group]
            db.add(user)
        await db.flush()
        db.add(NextPlan(user_id=1, user_template_id=None, data_limit=500))
        await db.execute(
            insert(UserUsageResetLogs),
            [{"user_id": uid, "used_traffic_at_reset": n} for uid in (1, 2) for n in (10, 20, 30)],
        )
        await db.commit()
    try:
        async with factory() as db:
            yield db
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["add_groups", "remove_groups", "expire", "datalimit", "proxy"])
async def test_bulk_reload_preserves_result_without_loading_history(bulk_db, action):
    db = bulk_db
    if action == "remove_groups":
        model = BulkGroup(users={1, 2, 3}, group_ids={2})
        run = bulk.remove_groups_from_users
        expected_ids = {1, 2, 3}
    elif action == "add_groups":
        model = BulkGroup(users={1, 2, 3}, group_ids={1})
        run = bulk.add_groups_to_users
        expected_ids = {1, 2}
    elif action == "expire":
        # Only the expired users are returned for node synchronization.
        await db.execute(update(User).where(User.id.in_([1, 2])).values(status=UserStatus.expired))
        await db.commit()
        model = BulkUser(users={1, 2, 3}, amount=2 * 86400)
        run = bulk.update_users_expire
        expected_ids = {1, 2}
    elif action == "datalimit":
        model = BulkUser(users={1, 2, 3}, amount=100)
        run = bulk.update_users_datalimit
        expected_ids = {1, 2}
    else:
        model = BulkUsersProxy(users={1, 2, 3}, method="xchacha20-poly1305")
        run = bulk.update_users_proxy_settings
        expected_ids = {1, 2, 3}

    history_loads = []

    def on_history_load(target, context):
        history_loads.append(target.id)

    event.listen(UserUsageResetLogs, "load", on_history_load)
    try:
        users, count = await run(db, model)
        assert count == 3
        assert {user.id for user in users} == expected_ids
        for user in users:
            response = UserResponse.model_validate(user)
            assert response.lifetime_used_traffic == (160 if user.id < 3 else 100)
            assert user.admin.role.name == "bulk-role"
            assert (response.next_plan.data_limit if response.next_plan else None) == (500 if user.id == 1 else None)
            if action == "add_groups":
                assert set(response.group_ids) == {1, 2}
            elif action == "remove_groups":
                assert set(response.group_ids) == ({1} if user.id == 3 else set())
            elif action == "proxy":
                assert user.proxy_settings["shadowsocks"] == {"password": "x" * 32, "method": "xchacha20-poly1305"}
            else:
                assert user.status == UserStatus.active
                if action == "datalimit":
                    assert user.data_limit == 200
                else:
                    assert user.expire > datetime.now(UTC)
        assert history_loads == []
        outside_user = await db.get(User, 4)
        assert outside_user.data_limit == 100
        assert outside_user.status == UserStatus.disabled
        assert outside_user.proxy_settings["shadowsocks"]["method"] == "aes-128-gcm"
    finally:
        event.remove(UserUsageResetLogs, "load", on_history_load)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["add_groups", "remove_groups"])
async def test_bulk_groups_refresh_already_loaded_memberships(bulk_db, action):
    # expire_on_commit=False must not leave the pre-mutation group collection cached.
    user = (await bulk_db.execute(select(User).where(User.id == 1).options(selectinload(User.groups)))).scalar_one()
    assert {group.id for group in user.groups} == {2}
    if action == "add_groups":
        users, count = await bulk.add_groups_to_users(bulk_db, BulkGroup(users={1}, group_ids={1}))
        expected = {1, 2}
    else:
        users, count = await bulk.remove_groups_from_users(bulk_db, BulkGroup(users={1}, group_ids={2}))
        expected = set()
    assert count == 1
    assert users[0] is user
    assert {group.id for group in user.groups} == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("additional_users", [60, 510])
async def test_bulk_datalimit_reload_queries_are_batched(bulk_db, additional_users):
    await bulk_db.execute(
        insert(User),
        [
            {
                "username": f"scale-{i}",
                "admin_id": 1,
                "status": UserStatus.limited,
                "used_traffic": 100,
                "data_limit": 100,
                "created_at": datetime.now(UTC),
            }
            for i in range(additional_users)
        ],
    )
    await bulk_db.commit()
    queries = []

    def count_query(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(bulk_db.bind.sync_engine, "before_cursor_execute", count_query)
    try:
        users, count = await bulk.update_users_datalimit(bulk_db, BulkUser(admins={1}, amount=100))
    finally:
        event.remove(bulk_db.bind.sync_engine, "before_cursor_execute", count_query)
    assert count == additional_users + 4
    assert len(users) == additional_users + 2
    assert all(user.status == UserStatus.active for user in users)
    # Count + target IDs + UPDATE + user/admin/next-plan SELECT + role + groups.
    # Above SQLAlchemy's 500-parent selectin batch size, one extra group query is expected.
    assert len(queries) <= (6 if additional_users < 500 else 7)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["expire", "datalimit"])
async def test_bulk_negative_adjustment_only_returns_newly_inactive_users(bulk_db, action):
    if action == "expire":
        await bulk_db.execute(
            update(User)
            .where(User.id.in_([1, 2]))
            .values(status=UserStatus.active, expire=datetime.now(UTC) + timedelta(days=1))
        )
        run = bulk.update_users_expire
        amount = -2 * 86400
        expected_status = UserStatus.expired
    else:
        await bulk_db.execute(update(User).where(User.id.in_([1, 2])).values(status=UserStatus.active, data_limit=200))
        run = bulk.update_users_datalimit
        amount = -100
        expected_status = UserStatus.limited
    await bulk_db.commit()
    users, count = await run(bulk_db, BulkUser(users={1, 2, 3}, amount=amount))
    assert count == (3 if action == "expire" else 2)
    assert {user.id for user in users} == {1, 2}
    assert all(user.status == expected_status for user in users)
    assert all(UserResponse.model_validate(user).lifetime_used_traffic == 160 for user in users)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["add_groups", "remove_groups", "expire", "datalimit"])
async def test_bulk_scope_without_sync_changes(bulk_db, action):
    if action == "add_groups":
        result = await bulk.add_groups_to_users(bulk_db, BulkGroup(users={3}, group_ids={1}))
    elif action == "remove_groups":
        result = await bulk.remove_groups_from_users(bulk_db, BulkGroup(users={1}, group_ids={1}))
    elif action == "expire":
        result = await bulk.update_users_expire(bulk_db, BulkUser(users={3}, amount=100))
    else:
        result = await bulk.update_users_datalimit(bulk_db, BulkUser(users={3}, amount=100))
    assert result == ([], 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["add_groups", "remove_groups", "expire", "datalimit", "proxy"])
async def test_bulk_empty_scope(bulk_db, action):
    if action in {"add_groups", "remove_groups"}:
        model = BulkGroup(users={999}, group_ids={1})
        run = bulk.add_groups_to_users if action == "add_groups" else bulk.remove_groups_from_users
    elif action == "proxy":
        model = BulkUsersProxy(users={999}, method="xchacha20-poly1305")
        run = bulk.update_users_proxy_settings
    else:
        model = BulkUser(users={999}, amount=100)
        run = bulk.update_users_expire if action == "expire" else bulk.update_users_datalimit
    assert await run(bulk_db, model) == ([], 0)
