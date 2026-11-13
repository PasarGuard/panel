import asyncio
import os

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import base
from app.db.crud.admin import reset_admin_usage
from app.db.models import Admin, AdminRole, AdminStatus, AdminUsageLogs
from config import database_settings


def _database_url(tmp_path) -> str:
    if os.getenv("TEST_FROM", "local").lower() == "local":
        return f"sqlite+aiosqlite:///{tmp_path / 'reset_admin_usage.db'}"
    return database_settings.url


@pytest.fixture
async def session_factory(tmp_path):
    url = _database_url(tmp_path)
    connect_args = {"timeout": 30} if url.startswith("sqlite") else {}
    engine = create_async_engine(url, poolclass=NullPool, connect_args=connect_args)

    proxy_column = base.Base.metadata.tables["users"].c.proxy_settings
    proxy_default = proxy_column.server_default
    if url.startswith("mysql"):
        proxy_column.server_default = None

    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.drop_all)
        await conn.run_sync(base.Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with factory() as seed:
        seed.add_all(
            [
                AdminRole(name="owner", is_owner=True, permissions={}, limits={}, features={}, access={}),
                AdminRole(name="administrator", is_owner=False, permissions={}, limits={}, features={}, access={}),
                AdminRole(name="operator", is_owner=False, permissions={}, limits={}, features={}, access={}),
            ]
        )
        await seed.commit()

    try:
        yield factory
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(base.Base.metadata.drop_all)
            await conn.run_sync(base.Base.metadata.create_all)
        await engine.dispose()
        proxy_column.server_default = proxy_default


async def _seed_admin(factory, *, used_traffic: int, status: AdminStatus = AdminStatus.active) -> int:
    async with factory() as session:
        operator_role = (await session.execute(select(AdminRole.id).where(AdminRole.name == "operator"))).scalar_one()
        admin = Admin(
            username=f"reseller{used_traffic}",
            hashed_password="x",
            role_id=operator_role,
            used_traffic=used_traffic,
            status=status,
        )
        session.add(admin)
        await session.commit()
        return admin.id


async def _stored(factory, admin_id: int) -> tuple[int, AdminStatus, list[int]]:
    async with factory() as session:
        used_traffic, status = (
            await session.execute(select(Admin.used_traffic, Admin.status).where(Admin.id == admin_id))
        ).one()
        logged = (
            (
                await session.execute(
                    select(AdminUsageLogs.used_traffic_at_reset)
                    .where(AdminUsageLogs.admin_id == admin_id)
                    .order_by(AdminUsageLogs.id)
                )
            )
            .scalars()
            .all()
        )
        return used_traffic, status, list(logged)


async def test_bytes_billed_between_the_read_and_the_reset_survive(session_factory):
    admin_id = await _seed_admin(session_factory, used_traffic=1000)

    async with session_factory() as reset_session:
        db_admin = (await reset_session.execute(select(Admin).where(Admin.id == admin_id))).scalar_one()
        assert db_admin.used_traffic == 1000

        async with session_factory() as tick_session:
            await tick_session.execute(
                update(Admin).where(Admin.id == admin_id).values(used_traffic=Admin.used_traffic + 300)
            )
            await tick_session.commit()

        returned = await reset_admin_usage(reset_session, db_admin)
        assert returned.used_traffic >= 0

    used_traffic, _, logged = await _stored(session_factory, admin_id)
    assert used_traffic >= 0
    assert len(logged) == 1
    assert used_traffic + sum(logged) == 1300


async def _load(session, admin_id: int) -> Admin:
    return (await session.execute(select(Admin).where(Admin.id == admin_id))).scalar_one()


async def test_a_second_reset_from_a_stale_copy_does_not_subtract_again(session_factory):
    admin_id = await _seed_admin(session_factory, used_traffic=1000)

    async with session_factory() as first, session_factory() as second:
        first_copy = await _load(first, admin_id)
        second_copy = await _load(second, admin_id)
        await reset_admin_usage(first, first_copy)
        returned = await reset_admin_usage(second, second_copy)
        assert returned.used_traffic == 0

    used_traffic, _, logged = await _stored(session_factory, admin_id)
    assert used_traffic == 0
    assert logged == [1000]


async def test_concurrent_resets_of_one_admin_log_the_usage_once(session_factory):
    admin_id = await _seed_admin(session_factory, used_traffic=1000)

    async with session_factory() as first, session_factory() as second:
        first_copy = await _load(first, admin_id)
        second_copy = await _load(second, admin_id)
        await asyncio.gather(reset_admin_usage(first, first_copy), reset_admin_usage(second, second_copy))

    used_traffic, _, logged = await _stored(session_factory, admin_id)
    assert used_traffic == 0
    assert logged == [1000]


async def test_usage_billed_concurrently_with_a_reset_is_kept(session_factory):
    admin_id = await _seed_admin(session_factory, used_traffic=1000)

    async def bill(amount: int) -> None:
        async with session_factory() as tick_session:
            await tick_session.execute(
                update(Admin).where(Admin.id == admin_id).values(used_traffic=Admin.used_traffic + amount)
            )
            await tick_session.commit()

    async with session_factory() as reset_session:
        db_admin = await _load(reset_session, admin_id)
        await asyncio.gather(bill(300), reset_admin_usage(reset_session, db_admin), bill(200))

    used_traffic, _, logged = await _stored(session_factory, admin_id)
    assert used_traffic >= 0
    assert len(logged) == 1
    assert used_traffic + sum(logged) == 1500


async def test_a_limited_admin_is_reactivated_by_the_reset(session_factory):
    admin_id = await _seed_admin(session_factory, used_traffic=4096, status=AdminStatus.limited)

    async with session_factory() as session:
        db_admin = (await session.execute(select(Admin).where(Admin.id == admin_id))).scalar_one()
        returned = await reset_admin_usage(session, db_admin)
        assert returned.status == AdminStatus.active
        assert returned.last_status_change is not None

    used_traffic, status, logged = await _stored(session_factory, admin_id)
    assert used_traffic == 0
    assert status == AdminStatus.active
    assert logged == [4096]


async def test_an_admin_with_no_usage_writes_no_log(session_factory):
    admin_id = await _seed_admin(session_factory, used_traffic=0)

    async with session_factory() as session:
        db_admin = (await session.execute(select(Admin).where(Admin.id == admin_id))).scalar_one()
        returned = await reset_admin_usage(session, db_admin)
        assert returned.used_traffic == 0

    used_traffic, status, logged = await _stored(session_factory, admin_id)
    assert used_traffic == 0
    assert status == AdminStatus.active
    assert logged == []


def _values(parameters) -> list:
    return list(parameters.values()) if isinstance(parameters, dict) else list(parameters)


async def test_traffic_added_between_the_locked_read_and_the_write_is_kept(session_factory):
    admin_id = await _seed_admin(session_factory, used_traffic=1000)
    engine = session_factory.kw["bind"]
    injected = []

    def add_traffic_before_the_write(conn, cursor, statement, parameters, context, executemany):
        if not injected and statement.lstrip().upper().startswith("UPDATE ADMINS"):
            injected.append(50)
            cursor.execute(f"UPDATE admins SET used_traffic = used_traffic + 50 WHERE id = {int(admin_id)}")

    async with session_factory() as session:
        db_admin = await _load(session, admin_id)
        event.listen(engine.sync_engine, "before_cursor_execute", add_traffic_before_the_write)
        try:
            await reset_admin_usage(session, db_admin)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", add_traffic_before_the_write)

    used_traffic, _, logged = await _stored(session_factory, admin_id)
    assert injected == [50]
    assert logged == [1000]
    assert used_traffic == 50


async def test_used_traffic_is_read_once_under_a_row_lock_and_that_value_is_logged_and_subtracted(session_factory):
    admin_id = await _seed_admin(session_factory, used_traffic=1000)
    engine = session_factory.kw["bind"]
    executed = []
    selects = []
    committed = []

    def record_sql(conn, cursor, statement, parameters, context, executemany):
        if not committed:
            executed.append((" ".join(statement.split()).lower(), _values(parameters)))

    def record_commit(conn):
        committed.append(True)

    def record_select(state):
        if not committed and state.is_select:
            selects.append(state.statement)

    async with session_factory() as session:
        db_admin = await _load(session, admin_id)
        event.listen(engine.sync_engine, "before_cursor_execute", record_sql)
        event.listen(engine.sync_engine, "commit", record_commit)
        event.listen(session.sync_session, "do_orm_execute", record_select)
        try:
            await reset_admin_usage(session, db_admin)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", record_sql)
            event.remove(engine.sync_engine, "commit", record_commit)
            event.remove(session.sync_session, "do_orm_execute", record_select)

    used_traffic, _, logged = await _stored(session_factory, admin_id)
    assert used_traffic == 0
    assert logged == [1000]

    reads = [sql for sql, _ in executed if "admins.used_traffic" in sql and " from admins " in f"{sql} "]
    assert len(reads) == 1

    locking_reads = [stmt for stmt in selects if [column.key for column in stmt.selected_columns] == ["used_traffic"]]
    assert len(locking_reads) == 1
    assert "FOR UPDATE" in str(locking_reads[0].compile(dialect=mysql.dialect()))
    assert "FOR UPDATE" in str(locking_reads[0].compile(dialect=postgresql.dialect()))

    subtractions = [(sql, values) for sql, values in executed if sql.startswith("update admins ")]
    assert len(subtractions) == 1
    subtraction_sql, subtraction_values = subtractions[0]
    assert "admins.used_traffic -" in subtraction_sql
    assert logged[0] in subtraction_values

    log_inserts = [values for sql, values in executed if sql.startswith("insert into admin_usage_logs")]
    assert len(log_inserts) == 1
    assert logged[0] in log_inserts[0]
