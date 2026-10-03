"""Group list/detail must not hydrate members; syncing a group's users must not query inbounds per user."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import event, insert, inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.crud.group import get_group, get_group_by_id, load_group_attrs
from app.db.crud.user import get_users
from app.db.crud.wireguard import get_users_accessible_tags
from app.db.models import Group, ProxyInbound, User, users_groups_association
from app.models.group import GroupListQuery, GroupResponse
from app.models.user import UserListQuery
from app.operation.group import GroupOperation

USERS = 30


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        inbounds = [ProxyInbound(tag="in-a"), ProxyInbound(tag="in-b")]
        big = Group(name="big", inbounds=[inbounds[0]])
        other = Group(name="other", inbounds=[inbounds[1]])
        empty = Group(name="empty", inbounds=[])
        session.add_all([*inbounds, big, other, empty])
        await session.flush()
        await session.execute(
            insert(User),
            [{"username": f"user{i}", "created_at": datetime.now(UTC), "proxy_settings": {}} for i in range(USERS)],
        )
        user_ids = (await session.execute(select(User.id))).scalars().all()
        rows = [{"user_id": uid, "groups_id": big.id} for uid in user_ids]
        rows += [{"user_id": uid, "groups_id": other.id} for uid in user_ids[::2]]
        await session.execute(insert(users_groups_association), rows)
        await session.commit()
        session.expunge_all()  # force fresh loads, like a new request
        yield session

    await engine.dispose()


def _record_statements(session):
    statements: list[str] = []

    @event.listens_for(session.bind.sync_engine, "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.split()))

    return statements


@pytest.mark.asyncio
async def test_get_group_counts_users_in_sql_without_loading_them(db_session):
    statements = _record_statements(db_session)

    groups, total = await get_group(db_session, GroupListQuery())

    assert total == 3
    assert {g.name: GroupResponse.model_validate(g).total_users for g in groups} == {
        "big": USERS,
        "other": (USERS + 1) // 2,
        "empty": 0,
    }
    assert all("users" in sa_inspect(g).unloaded for g in groups)
    assert not any("FROM users " in s or "JOIN users " in s for s in statements)


@pytest.mark.asyncio
async def test_get_group_by_id_and_load_group_attrs_do_not_load_users(db_session):
    group_id = (await db_session.execute(select(Group.id).where(Group.name == "big"))).scalar_one()

    group = await get_group_by_id(db_session, group_id)
    assert GroupResponse.model_validate(group).total_users == USERS
    assert "users" in sa_inspect(group).unloaded

    await load_group_attrs(db_session, group)
    assert group.total_users == USERS
    assert "users" in sa_inspect(group).unloaded


@pytest.mark.asyncio
async def test_get_users_load_group_inbounds_avoids_per_user_inbound_queries(db_session):
    statements = _record_statements(db_session)

    users = await get_users(
        db_session,
        UserListQuery(group_ids=[1]),
        load_usage_logs=False,
        load_group_inbounds=True,
    )
    assert len(users) == USERS

    statements.clear()
    tags = [await user.inbounds() for user in users]

    assert statements == []  # every group's inbounds were already loaded
    assert all("in-a" in user_tags for user_tags in tags)
    assert sum("in-b" in user_tags for user_tags in tags) == (USERS + 1) // 2


def _record_bind_counts(session):
    counts: list[int] = []

    @event.listens_for(session.bind.sync_engine, "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):
        counts.append(len(parameters))

    return counts


@pytest.mark.asyncio
async def test_get_users_accessible_tags_chunks_large_id_lists(db_session):
    # asyncpg rejects statements with more than 32767 bind parameters.
    counts = _record_bind_counts(db_session)

    tags = await get_users_accessible_tags(db_session, list(range(1, 25_001)))

    assert max(counts) <= 10_000
    assert len(counts) == 3
    assert "in-a" in tags[1] and "in-b" not in tags[2]


@pytest.mark.asyncio
async def test_get_users_for_sync_chunks_large_username_lists(db_session):
    counts = _record_bind_counts(db_session)

    names = [f"user{i}" for i in range(USERS)] + [f"missing{i}" for i in range(25_000)]
    users = await GroupOperation._get_users_for_sync(db_session, names)

    assert len(users) == USERS
    assert max(counts) <= 10_000
