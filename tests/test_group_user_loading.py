"""Group list/detail must not hydrate members; syncing a group's users must not query inbounds per user."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import event, func, insert, inspect as sa_inspect, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.crud.bulk import (
    add_groups_to_users,
    remove_groups_from_users,
    reset_all_users_data_usage,
    update_users_datalimit,
    update_users_expire,
    update_users_proxy_settings,
)
from app.db.crud.group import get_group, get_group_by_id, get_group_usernames, load_group_attrs, remove_group
from app.db.crud.user import get_users, get_users_by_ids, remove_users
from app.db.crud.wireguard import get_users_accessible_tags
from app.db.models import (
    Admin,
    Group,
    ProxyInbound,
    User,
    UserStatus,
    UserTemplate,
    UserUsageResetLogs,
    inbounds_groups_association,
    template_group_association,
    users_groups_association,
)
from app.models.group import BulkGroup, BulkGroupSelection, GroupListQuery, GroupResponse
from app.models.proxy import ShadowsocksMethods
from app.models.user import BulkUser, BulkUsersProxy, UserListQuery
from app.operation import OperatorType
from app.operation.admin import AdminOperation
from app.operation.group import GroupOperation
from app.operation.user import UserOperation

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

    assert sorted(await get_group_usernames(db_session, [big_id])) == sorted(f"user{i}" for i in range(USERS))

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
async def test_get_group_usernames_is_distinct_and_chunks_large_id_lists(db_session):
    counts = _record_bind_counts(db_session)
    big_id, other_id = await _group_id(db_session, "big"), await _group_id(db_session, "other")

    # every "other" member is also in "big": a user in several of the groups is returned once
    names = await get_group_usernames(db_session, [big_id, other_id] + list(range(1_000, 26_000)))

    assert sorted(names) == sorted(f"user{i}" for i in range(USERS))
    assert max(counts) <= 10_000


def _stub_node_sync(monkeypatch) -> list[User]:
    synced: list[User] = []

    async def fake_sync_users(users):
        synced.extend(users)

    async def fake_notify(*args):
        return None

    monkeypatch.setattr("app.operation.group.sync_users", fake_sync_users)
    monkeypatch.setattr("app.operation.group.notification", SimpleNamespace(remove_group=fake_notify))
    return synced


async def _remove_via_operation(session, how, names):
    ids = {await _group_id(session, name) for name in names}
    admin = SimpleNamespace(is_owner=True, role=None, username="tester")
    operation = GroupOperation(OperatorType.API)
    if how == "remove_group":
        (group_id,) = ids
        await operation.remove_group(session, group_id, admin)
    else:
        await operation.bulk_remove_groups_by_id(session, BulkGroupSelection(ids=ids), admin)


@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["remove_group", "bulk_remove_groups_by_id"])
async def test_group_removal_syncs_users_without_the_removed_groups_inbounds(db_session, monkeypatch, how):
    synced = _stub_node_sync(monkeypatch)
    statements = _record_statements(db_session)

    await _remove_via_operation(db_session, how, ["big"])

    assert len(synced) == USERS
    statements.clear()
    tags = [await user.inbounds() for user in synced]
    assert statements == []  # the synced users carry their (post-removal) groups' inbounds
    # "big" (in-a) is gone; only the odd users lose all inbounds, the rest keep "other" (in-b)
    assert sorted(tags) == [[]] * (USERS // 2) + [["in-b"]] * ((USERS + 1) // 2)


@pytest.mark.asyncio
async def test_bulk_remove_groups_by_id_syncs_each_member_once_without_any_removed_inbounds(db_session, monkeypatch):
    synced = _stub_node_sync(monkeypatch)
    statements = _record_statements(db_session)

    await _remove_via_operation(db_session, "bulk_remove_groups_by_id", ["big", "other"])

    assert len(synced) == USERS  # members of both groups are synced once
    statements.clear()
    assert [await user.inbounds() for user in synced] == [[]] * USERS
    assert statements == []


@pytest.mark.asyncio
async def test_bulk_group_filter_with_40k_explicit_ids_binds_no_id_parameters(db_session):
    # asyncpg rejects statements with more than 32767 bind parameters; the explicit ids are OR-combined with
    # the other conditions, so they cannot be chunked.
    user_ids = (await db_session.execute(select(User.id).order_by(User.id))).scalars().all()
    other_id, empty_id = await _group_id(db_session, "other"), await _group_id(db_session, "empty")
    explicit = set(user_ids[:5]) | set(range(100_000, 140_000))  # 5 members and 40k ids that match nothing
    bulk = BulkGroup(group_ids={empty_id}, has_group_ids={other_id}, users=explicit)
    counts = _record_bind_counts(db_session)

    users, effective = await add_groups_to_users(db_session, bulk)

    # OR semantics: the 5 explicit users plus the 15 "other" members, where users 0, 2 and 4 are in both
    assert effective == 17
    assert sorted(user.id for user in users) == sorted(set(user_ids[:5]) | set(user_ids[::2]))
    assert await _count_members(db_session, empty_id) == 17
    assert max(counts) <= 10_000


async def _prepare_explicit_users(session):
    user_ids = (await session.execute(select(User.id).order_by(User.id))).scalars().all()
    await session.execute(
        update(User).values(
            expire=datetime.now(UTC) + timedelta(hours=1), data_limit=1000, used_traffic=500, proxy_settings={}
        )
    )
    await session.commit()
    session.expunge_all()
    return user_ids[:5], set(user_ids[:5]) | set(range(100_000, 140_000))  # 5 users and 40k ids that match nothing


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation,model",
    [
        (update_users_expire, lambda users: BulkUser(amount=-7200, users=users)),
        (update_users_datalimit, lambda users: BulkUser(amount=-600, users=users)),
        (
            update_users_proxy_settings,
            lambda users: BulkUsersProxy(method=ShadowsocksMethods.AES_256_GCM, users=users),
        ),
    ],
)
async def test_bulk_user_ops_with_40k_explicit_ids_and_preloaded_inbounds(db_session, operation, model):
    members, explicit = await _prepare_explicit_users(db_session)
    counts = _record_bind_counts(db_session)
    statements = _record_statements(db_session)

    users, effective = await operation(db_session, model(explicit))

    assert effective == 5
    assert sorted(user.id for user in users) == sorted(members)
    assert max(counts) <= 10_000
    statements.clear()
    assert all("in-a" in tags for tags in [await user.inbounds() for user in users])
    assert statements == []  # the node sync reads inbounds from the preloaded groups


@pytest.mark.asyncio
async def test_reset_all_users_data_usage_binds_no_user_ids(db_session):
    await _add_big_group_members(db_session, 12_000)
    first_user = (await db_session.execute(select(User.id).order_by(User.id).limit(1))).scalar_one()
    db_session.add(UserUsageResetLogs(user_id=first_user, used_traffic_at_reset=7))
    await db_session.execute(update(User).values(used_traffic=100, status=UserStatus.limited))
    await db_session.execute(update(User).where(User.id <= 5).values(admin_id=1))
    await db_session.commit()
    counts = _record_bind_counts(db_session)

    await reset_all_users_data_usage(db_session, SimpleNamespace(id=1))  # scoped to one admin's users

    statuses = lambda: select(User.status, func.count()).group_by(User.status)
    assert dict((await db_session.execute(statuses())).all()) == {
        UserStatus.active: 5,
        UserStatus.limited: 12_000 + USERS - 5,
    }
    assert (await db_session.execute(select(func.count()).select_from(UserUsageResetLogs))).scalar_one() == 0

    await reset_all_users_data_usage(db_session)

    assert dict((await db_session.execute(statuses())).all()) == {UserStatus.active: 12_000 + USERS}
    assert (await db_session.execute(select(func.sum(User.used_traffic)))).scalar_one() == 0
    assert max(counts) <= 10_000


@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["activate", "disable"])
async def test_admin_bulk_activate_and_disable_sync_users_without_usage_logs_or_inbound_queries(
    db_session, monkeypatch, how
):
    admin = Admin(username="adm", hashed_password="x")
    db_session.add(admin)
    await db_session.flush()
    before, after = (UserStatus.disabled, UserStatus.active) if how == "activate" else (UserStatus.active, None)
    await db_session.execute(update(User).values(admin_id=admin.id, status=before))
    await db_session.commit()
    db_session.expunge_all()
    admin = await db_session.get(Admin, admin.id)
    synced: list[User] = []

    async def fake_sync_users(users):
        synced.extend(users)

    monkeypatch.setattr("app.operation.admin.sync_users", fake_sync_users)
    statements = _record_statements(db_session)
    operation = AdminOperation(OperatorType.API)
    actor = SimpleNamespace(username="tester")

    if how == "activate":
        await operation._activate_all_disabled_users_for_admin(db_session, admin, actor)
    else:
        await operation._disable_all_active_users_for_admin(db_session, admin, actor)

    assert len(synced) == USERS
    assert all("usage_logs" in sa_inspect(user).unloaded for user in synced)
    if after is not None:
        assert all(user.status == after for user in synced)
        statements.clear()
        assert all("in-a" in tags for tags in [await user.inbounds() for user in synced])
        assert statements == []


@pytest.mark.asyncio
async def test_by_id_user_loading_with_40k_ids_binds_no_id_parameters(db_session):
    # The by-id bulk endpoints (disable, reset usage, revoke, apply template, ...) load the requested users with
    # `ids` taken from the request body; asyncpg rejects statements with more than 32767 bind parameters.
    ids = list(range(1, 40_001))
    counts = _record_bind_counts(db_session)

    by_query = await get_users(db_session, UserListQuery(ids=ids, limit=len(ids)))
    by_ids = await get_users_by_ids(db_session, ids)

    assert len(by_query) == len(by_ids) == USERS
    assert max(counts) <= 10_000


@pytest.mark.asyncio
async def test_remove_users_binds_no_id_parameters(db_session):
    await _add_big_group_members(db_session, 12_000)
    users = await get_users_by_ids(db_session, (await db_session.execute(select(User.id))).scalars().all())
    counts = _record_bind_counts(db_session)

    await remove_users(db_session, users)

    assert max(counts) <= 10_000
    assert (await db_session.execute(select(func.count()).select_from(User))).scalar_one() == 0
    assert (await db_session.execute(select(func.count()).select_from(users_groups_association))).scalar_one() == 0


@pytest.mark.asyncio
async def test_by_id_bulk_sync_reload_preloads_group_inbounds(db_session):
    statements = _record_statements(db_session)
    ids = (await db_session.execute(select(User.id))).scalars().all()

    users = await UserOperation(OperatorType.API)._load_users_by_ids(db_session, ids)

    assert len(users) == USERS
    statements.clear()
    assert all("in-a" in tags for tags in [await user.inbounds() for user in users])
    assert statements == []  # sync_users reads the inbounds from the preloaded groups
