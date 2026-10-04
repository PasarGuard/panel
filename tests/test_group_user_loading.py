"""Group list/detail must not hydrate members; syncing a group's users must not query inbounds per user."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import event, func, insert, inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.crud.bulk import add_groups_to_users, remove_groups_from_users
from app.db.crud.group import get_group, get_group_by_id, get_group_usernames, load_group_attrs, remove_group
from app.db.crud.user import get_users
from app.db.crud.wireguard import get_users_accessible_tags
from app.db.models import (
    Group,
    ProxyInbound,
    User,
    UserTemplate,
    inbounds_groups_association,
    template_group_association,
    users_groups_association,
)
from app.models.group import BulkGroup, GroupListQuery, GroupResponse
from app.models.user import UserListQuery
from app.operation import OperatorType
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


async def _group_id(session, name):
    return (await session.execute(select(Group.id).where(Group.name == name))).scalar_one()


async def _count_members(session, group_id):
    return (
        await session.execute(
            select(func.count())
            .select_from(users_groups_association)
            .where(users_groups_association.c.groups_id == group_id)
        )
    ).scalar_one()


async def _add_big_group_members(session, count):
    """`count` extra users in the "big" group only."""
    big_id = await _group_id(session, "big")
    now = datetime.now(UTC)
    await session.execute(
        insert(User),
        [{"username": f"extra{i}", "created_at": now, "proxy_settings": {}} for i in range(count)],
    )
    extra_ids = (await session.execute(select(User.id).where(User.username.like("extra%")))).scalars().all()
    await session.execute(
        insert(users_groups_association), [{"user_id": uid, "groups_id": big_id} for uid in extra_ids]
    )
    await session.commit()
    session.expunge_all()


@pytest.mark.asyncio
async def test_bulk_add_and_remove_groups_chunk_ids_and_preload_inbounds(db_session):
    # asyncpg rejects statements with more than 32767 bind parameters.
    await _add_big_group_members(db_session, 25_000)
    big_id, other_id = await _group_id(db_session, "big"), await _group_id(db_session, "other")
    bulk = BulkGroup(group_ids={other_id}, has_group_ids={big_id})
    counts = _record_bind_counts(db_session)
    statements = _record_statements(db_session)

    users, effective = await add_groups_to_users(db_session, bulk)

    # every in-scope user is in "big"; the 15 fixture users that already had "other" are not touched
    assert effective == 25_000 + USERS
    assert len(users) == 25_000 + USERS - (USERS + 1) // 2
    assert await _count_members(db_session, other_id) == 25_000 + USERS
    assert max(counts) <= 10_000
    statements.clear()
    assert all("in-b" in tags for tags in [await user.inbounds() for user in users])
    assert statements == []  # groups' inbounds were preloaded

    counts.clear()
    users, effective = await remove_groups_from_users(db_session, bulk)

    assert effective == 25_000 + USERS
    assert len(users) == 25_000 + USERS
    assert await _count_members(db_session, other_id) == 0
    assert await _count_members(db_session, big_id) == 25_000 + USERS
    assert max(counts) <= 10_000
    statements.clear()
    assert all(tags == ["in-a"] for tags in [await user.inbounds() for user in users])
    assert statements == []


@pytest.mark.asyncio
async def test_remove_group_deletes_association_rows_in_bulk(db_session):
    big_id = await _group_id(db_session, "big")
    other_id = await _group_id(db_session, "other")
    db_session.add(UserTemplate(name="tpl", username_prefix=None, username_suffix=None, extra_settings=None, groups=[]))
    await db_session.flush()
    template_id = (await db_session.execute(select(UserTemplate.id))).scalar_one()
    await db_session.execute(
        insert(template_group_association), [{"user_template_id": template_id, "group_id": big_id}]
    )
    await db_session.commit()
    db_session.expunge_all()
    group = await get_group_by_id(db_session, big_id)
    executemany: list[str] = []
    statements = _record_statements(db_session)

    @event.listens_for(db_session.bind.sync_engine, "before_cursor_execute")
    def _record_executemany(conn, cursor, statement, parameters, context, many):
        if many:
            executemany.append(statement)

    assert sorted(await get_group_usernames(db_session, big_id)) == sorted(f"user{i}" for i in range(USERS))

    await remove_group(db_session, group)

    assert executemany == []  # no per-member DELETE
    assert not any("FROM users " in s or "JOIN users " in s for s in statements[1:])  # members were never loaded
    assert group.id == big_id and group.name == "big"  # callers still log/notify with the deleted group
    assert (await db_session.execute(select(Group.id).where(Group.id == big_id))).first() is None
    assert await _count_members(db_session, big_id) == 0
    assert await _count_members(db_session, other_id) == (USERS + 1) // 2  # other groups keep their members
    for table, column in (
        (template_group_association, template_group_association.c.group_id),
        (inbounds_groups_association, inbounds_groups_association.c.group_id),
    ):
        assert (
            await db_session.execute(select(func.count()).select_from(table).where(column == big_id))
        ).scalar_one() == 0
    assert (await db_session.execute(select(func.count()).select_from(ProxyInbound))).scalar_one() == 2


@pytest.mark.asyncio
async def test_group_operation_remove_group_syncs_users_without_the_removed_groups_inbounds(db_session, monkeypatch):
    synced: list[User] = []

    async def fake_sync_users(users):
        synced.extend(users)

    async def fake_notify(*args):
        return None

    monkeypatch.setattr("app.operation.group.sync_users", fake_sync_users)
    monkeypatch.setattr("app.operation.group.notification", SimpleNamespace(remove_group=fake_notify))
    admin = SimpleNamespace(is_owner=True, role=None, username="tester")

    await GroupOperation(OperatorType.API).remove_group(db_session, await _group_id(db_session, "big"), admin)

    assert len(synced) == USERS
    # "big" (in-a) is gone; only the odd users lose all inbounds, the rest keep "other" (in-b)
    assert sorted([await user.inbounds() for user in synced]) == [[]] * (USERS // 2) + [["in-b"]] * ((USERS + 1) // 2)
