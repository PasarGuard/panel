import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import event, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload

from app.db import Base
from app.db.crud.user import get_admin_users_for_node_sync
from app.db.models import (
    Admin,
    AdminRole,
    AdminStatus,
    Group,
    NextPlan,
    ProxyInbound,
    User,
    UserStatus,
    UserUsageResetLogs,
)
from app.nats.proto_utils import serialize_proto_messages
from app.node import sync as node_sync
from app.operation import OperatorType
from app.operation.admin import AdminOperation
from app.operation.admin_sync import sync_admin_users_for_block_transition


@pytest.fixture
async def sync_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as db:
        role = AdminRole(name="sync-role")
        db.add(role)
        await db.flush()
        db.add_all(
            [Admin(username=name, hashed_password="test", role_id=role.id) for name in ("target", "other", "empty")]
        )
        shared = ProxyInbound(tag="shared")
        groups = [
            Group(name="enabled", inbounds=[shared, ProxyInbound(tag="enabled")]),
            Group(name="duplicate", inbounds=[shared]),
            Group(name="disabled", inbounds=[ProxyInbound(tag="disabled")], is_disabled=True),
        ]
        db.add_all(groups)
        await db.flush()
        statuses = [
            UserStatus.active,
            UserStatus.on_hold,
            UserStatus.disabled,
            UserStatus.limited,
            UserStatus.expired,
            UserStatus.active,
            UserStatus.active,
            UserStatus.active,
        ]
        for i, status in enumerate(statuses, 1):
            user = User(
                username=f"user-{i}",
                admin_id=1 if i < 8 else 2,
                status=status,
                proxy_settings={"trojan": {"password": f"password-{i}"}},
            )
            user.groups = groups if i < 6 or i == 8 else [groups[2]] if i == 6 else []
            if i == 3:
                user.on_hold_expire_duration = 3600
            db.add(user)
        await db.flush()
        db.add(NextPlan(user_id=1, user_template_id=None, data_limit=500))
        await db.execute(
            insert(UserUsageResetLogs),
            [{"user_id": uid, "used_traffic_at_reset": 100} for uid in range(1, 9) for _ in range(3)],
        )
        await db.commit()
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def dispatch(monkeypatch):
    messages = []

    async def capture(users):
        messages.extend(serialize_proto_messages(users))

    monkeypatch.setattr(node_sync, "_dispatch_users_update", capture)
    return messages


def observe(db):
    sql, history, plans = [], [], []

    def on_sql(conn, cursor, statement, parameters, context, executemany):
        sql.append(statement)

    def on_history(target, context):
        history.append(target.id)

    def on_plan(target, context):
        plans.append(target.id)

    event.listen(db.bind.sync_engine, "before_cursor_execute", on_sql)
    event.listen(UserUsageResetLogs, "load", on_history)
    event.listen(NextPlan, "load", on_plan)

    def cleanup():
        event.remove(db.bind.sync_engine, "before_cursor_execute", on_sql)
        event.remove(UserUsageResetLogs, "load", on_history)
        event.remove(NextPlan, "load", on_plan)

    return sql, history, plans, cleanup


async def admin_row(db, admin_id=1):
    return (await db.scalars(select(Admin).where(Admin.id == admin_id).options(joinedload(Admin.role)))).one()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,disconnect,was_blocked",
    [
        (AdminStatus.limited, True, False),
        (AdminStatus.disabled, True, False),
        (AdminStatus.active, True, True),
        (AdminStatus.limited, False, True),
        (AdminStatus.disabled, False, True),
    ],
)
async def test_admin_transition_keeps_scope_and_node_payload_without_history(
    sync_db, dispatch, status, disconnect, was_blocked
):
    async with sync_db() as db:
        admin = await admin_row(db)
        admin.status = status
        admin.role.disconnect_users_when_limited = disconnect
        admin.role.disconnect_users_when_disabled = disconnect
        await db.commit()
        sql, history, plans, cleanup = observe(db)
        try:
            count = await sync_admin_users_for_block_transition(db, admin, was_blocked)
            await asyncio.sleep(0)
            expected_ids = {1, 2, 6, 7} if not was_blocked else set(range(1, 8))
            assert count == len(expected_ids)
            assert {int(message["email"]) for message in dispatch} == expected_ids
            for message in dispatch:
                uid = int(message["email"])
                expected_tags = {"shared", "enabled"} if was_blocked and uid in (1, 2) else set()
                assert set(message.get("inbounds", [])) == expected_tags
            assert history == []
            assert plans == []
            assert len(sql) <= 3
        finally:
            cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,was_blocked", [(AdminStatus.active, False), (AdminStatus.limited, True), (AdminStatus.disabled, True)]
)
async def test_unchanged_block_state_does_not_load_or_dispatch_users(sync_db, dispatch, status, was_blocked):
    async with sync_db() as db:
        admin = await admin_row(db)
        admin.status = status
        await db.commit()
        sql, _, _, cleanup = observe(db)
        try:
            assert await sync_admin_users_for_block_transition(db, admin, was_blocked) == 0
            await asyncio.sleep(0)
            assert dispatch == []
            assert sql == []
        finally:
            cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("activate", [True, False])
@pytest.mark.parametrize("blocked", [True, False])
async def test_admin_user_actions_preserve_status_and_blocking(sync_db, dispatch, activate, blocked):
    async with sync_db() as db:
        admin = await admin_row(db)
        admin.status = AdminStatus.disabled if blocked else AdminStatus.active
        await db.commit()
        operation = AdminOperation(OperatorType.SYSTEM)
        action = (
            operation._activate_all_disabled_users_for_admin
            if activate
            else operation._disable_all_active_users_for_admin
        )
        _, history, plans, cleanup = observe(db)
        try:
            await action(db, admin, SimpleNamespace(username="operator"))
            await asyncio.sleep(0)
            assert {int(message["email"]) for message in dispatch} == (set() if blocked else set(range(1, 8)))
            for message in dispatch:
                uid = int(message["email"])
                assert set(message.get("inbounds", [])) == (
                    {"enabled", "shared"} if activate and uid in (1, 2, 3) else set()
                )
            assert history == []
            assert plans == []
        finally:
            cleanup()
        statuses = dict((await db.execute(select(User.id, User.status))).all())
        assert statuses == {
            1: UserStatus.active if activate else UserStatus.disabled,
            2: UserStatus.on_hold if activate else UserStatus.disabled,
            3: UserStatus.on_hold if activate else UserStatus.disabled,
            4: UserStatus.limited,
            5: UserStatus.expired,
            6: UserStatus.active if activate else UserStatus.disabled,
            7: UserStatus.active if activate else UserStatus.disabled,
            8: UserStatus.active,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("was_blocked", [True, False])
async def test_empty_admin_does_not_dispatch_other_users(sync_db, dispatch, was_blocked):
    async with sync_db() as db:
        admin = await admin_row(db, 3)
        admin.status = AdminStatus.active if was_blocked else AdminStatus.limited
        await db.commit()
        assert await sync_admin_users_for_block_transition(db, admin, was_blocked) == 0
        await asyncio.sleep(0)
        assert dispatch == []


@pytest.mark.asyncio
@pytest.mark.parametrize("user_count,max_queries", [(62, 3), (512, 5)])
async def test_node_sync_uses_batched_inbounds_without_per_user_queries(sync_db, dispatch, user_count, max_queries):
    async with sync_db() as db:
        group = (await db.scalars(select(Group).where(Group.id == 1))).one()
        for i in range(user_count - 7):
            user = User(username=f"extra-{i}", admin_id=1, proxy_settings={"trojan": {"password": "test"}})
            user.groups = [group]
            db.add(user)
        await db.commit()
    async with sync_db() as db:
        admin = await admin_row(db)
        sql, history, plans, cleanup = observe(db)
        try:
            assert await sync_admin_users_for_block_transition(db, admin, True) == user_count
            await asyncio.sleep(0)
            assert len(dispatch) == user_count
            assert len(sql) <= max_queries
            assert history == []
            assert plans == []
        finally:
            cleanup()


@pytest.mark.asyncio
async def test_sync_loader_can_serialize_detached_users_without_extra_reads(sync_db, dispatch):
    async with sync_db() as db:
        users = await get_admin_users_for_node_sync(db, 1)
        assert len(users) == 7
        assert all("usage_logs" not in user.__dict__ and "next_plan" not in user.__dict__ for user in users)
        assert all("note" not in user.__dict__ and "username" not in user.__dict__ for user in users)
    await node_sync.sync_users(users)
    await asyncio.sleep(0)
    for message in dispatch:
        uid = int(message["email"])
        assert set(message.get("inbounds", [])) == ({"enabled", "shared"} if uid in (1, 2) else set())
        assert message["proxies"]["trojan"]["password"] == f"password-{uid}"


@pytest.mark.asyncio
async def test_empty_status_filter_returns_no_users(sync_db):
    async with sync_db() as db:
        assert await get_admin_users_for_node_sync(db, 1, statuses=[]) == []
