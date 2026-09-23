from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.db import base
from app.db.crud.admin import get_admin_usages
from app.db.crud.node import get_nodes_usage
from app.db.crud.user import get_all_users_usages, get_user_usages
from app.db.models import Admin, AdminRole, AdminStatus, Node, NodeUsage, NodeUserUsage, System, User
from app.jobs import compact_usages, record_usages
from app.models.proxy import ProxyTable
from app.models.stats import Period
from app.operation import admin_sync
from config import database_settings


class DummyNode:
    def __init__(self, node_id: int, usage_coefficient: int = 1):
        self.node_id = node_id
        self._usage_coefficient = usage_coefficient

    async def get_extra(self) -> dict[str, Any]:
        return {"usage_coefficient": self._usage_coefficient}


def _get_test_database_url() -> str:
    test_from = os.getenv("TEST_FROM", "local").lower()
    if test_from == "local":
        return "sqlite+aiosqlite:///:memory:"
    return database_settings.url


@pytest.fixture
async def session_factory(monkeypatch: pytest.MonkeyPatch):
    database_url = _get_test_database_url()
    is_sqlite = database_url.startswith("sqlite")

    engine_kwargs = {}
    connect_args = {}
    if is_sqlite:
        connect_args["check_same_thread"] = False
        # Keep the in-memory database alive across connections
        engine_kwargs["poolclass"] = StaticPool
    else:
        engine_kwargs["poolclass"] = NullPool

    # MySQL/MariaDB do not allow defaults on JSON columns; strip them temporarily
    proxy_default = None
    proxy_column = None
    needs_json_default_fix = database_url.startswith("mysql")
    if needs_json_default_fix:
        users_table = base.Base.metadata.tables["users"]
        proxy_column = users_table.c.proxy_settings
        proxy_default = proxy_column.server_default
        proxy_column.server_default = None

    engine = create_async_engine(database_url, connect_args=connect_args, **engine_kwargs)
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.drop_all)
        await conn.run_sync(base.Base.metadata.create_all)

    # Seed the 3 default roles so FK constraints on admins.role_id are satisfied
    async with async_sessionmaker(bind=engine, expire_on_commit=False)() as seed_session:
        seed_session.add_all(
            [
                AdminRole(name="owner", is_owner=True, permissions={}, limits={}, features={}, access={}),
                AdminRole(name="administrator", is_owner=False, permissions={}, limits={}, features={}, access={}),
                AdminRole(name="operator", is_owner=False, permissions={}, limits={}, features={}, access={}),
            ]
        )
        await seed_session.commit()

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    class TestGetDB:
        def __init__(self):
            self.db = session_factory()

        async def __aenter__(self):
            return self.db

        async def __aexit__(self, exc_type, exc_value, traceback):
            if isinstance(exc_value, SQLAlchemyError):
                await self.db.rollback()
            await self.db.close()

    monkeypatch.setattr(record_usages, "engine", engine)
    monkeypatch.setattr(record_usages, "GetDB", TestGetDB)
    monkeypatch.setattr(compact_usages, "GetDB", TestGetDB)
    monkeypatch.setattr(admin_sync, "GetDB", TestGetDB)

    yield session_factory

    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.drop_all)
    await engine.dispose()
    if needs_json_default_fix and proxy_column is not None:
        proxy_column.server_default = proxy_default


@pytest.mark.asyncio
async def test_record_user_usages_updates_users_and_admins(monkeypatch: pytest.MonkeyPatch, session_factory):
    async with session_factory() as session:
        admin = Admin(username="admin", hashed_password="secret", role_id=3)
        session.add(admin)
        await session.flush()
        admin_id = admin.id

        user_one = User(username="user1", admin_id=admin_id, proxy_settings=ProxyTable().dict(no_obj=True))
        user_two = User(username="user2", admin_id=admin_id, proxy_settings=ProxyTable().dict(no_obj=True))
        session.add_all([user_one, user_two])
        await session.flush()
        user_one_id, user_two_id = user_one.id, user_two.id

        node_one = Node(
            name="node-1",
            address="10.0.0.1",
            port=1000,
            api_port=1001,
            server_ca="ca1",
            api_key="key1",
            core_config_id=None,
        )
        node_two = Node(
            name="node-2",
            address="10.0.0.2",
            port=1001,
            api_port=1002,
            server_ca="ca2",
            api_key="key2",
            core_config_id=None,
        )
        session.add_all([node_one, node_two])
        await session.flush()
        node_one_id, node_two_id = node_one.id, node_two.id
        await session.commit()

    nodes = [
        (node_one_id, DummyNode(node_one_id, usage_coefficient=2)),
        (node_two_id, DummyNode(node_two_id, usage_coefficient=1)),
    ]
    monkeypatch.setattr(record_usages.node_manager, "get_healthy_nodes", AsyncMock(return_value=nodes))

    stats_map = {
        node_one_id: [{"uid": str(user_one_id), "value": 100}, {"uid": str(user_two_id), "value": 50}],
        node_two_id: [{"uid": str(user_one_id), "value": 75}],
    }

    async def fake_get_users_stats(node: DummyNode, node_id: int | None = None):
        return stats_map[node.node_id]

    monkeypatch.setattr(record_usages, "get_users_stats", fake_get_users_stats)
    monkeypatch.setattr(record_usages.usage_settings, "disable_recording_node_usage", False)

    await record_usages.record_user_usages()

    async with session_factory() as session:
        users_result = await session.execute(
            select(User.id, User.used_traffic, User.online_at).where(User.id.in_([user_one_id, user_two_id]))
        )
        user_rows = users_result.all()
        user_totals = {row.id: (row.used_traffic, row.online_at) for row in user_rows}

        assert user_totals[user_one_id][0] > user_totals[user_two_id][0]
        assert all(total > 0 for total, _ in user_totals.values())
        assert all(online_at is not None for _, online_at in user_totals.values())

        admin_total = await session.execute(select(Admin.used_traffic).where(Admin.id == admin_id))
        admin_used = admin_total.scalar_one()
        assert admin_used == sum(total for total, _ in user_totals.values())

        node_usage_rows = await session.execute(
            select(NodeUserUsage.node_id, NodeUserUsage.user_id, NodeUserUsage.used_traffic)
        )
        node_usage_records = node_usage_rows.all()
        usage_pairs = {(row.node_id, row.user_id) for row in node_usage_records}
        assert usage_pairs == {
            (node_one_id, user_one_id),
            (node_one_id, user_two_id),
            (node_two_id, user_one_id),
        }

        aggregated_usage = defaultdict(int)
        for record in node_usage_records:
            assert record.used_traffic > 0
            aggregated_usage[record.user_id] += record.used_traffic

        for user_id, (total_usage, _) in user_totals.items():
            assert aggregated_usage[user_id] == total_usage


@pytest.mark.asyncio
async def test_record_user_usages_limits_overused_admin(monkeypatch: pytest.MonkeyPatch, session_factory):
    async with session_factory() as session:
        admin = Admin(username="limited-admin", hashed_password="secret", role_id=3, data_limit=100)
        session.add(admin)
        await session.flush()
        admin_id = admin.id

        user = User(username="limited-user", admin_id=admin_id, proxy_settings=ProxyTable().dict(no_obj=True))
        node = Node(
            name="node-1",
            address="10.0.0.1",
            port=1000,
            api_port=1001,
            server_ca="ca1",
            api_key="key1",
            core_config_id=None,
        )
        session.add_all([user, node])
        await session.flush()
        user_id, node_id = user.id, node.id
        await session.commit()

    monkeypatch.setattr(
        record_usages.node_manager, "get_healthy_nodes", AsyncMock(return_value=[(node_id, DummyNode(node_id))])
    )

    async def fake_get_users_stats(_: DummyNode, node_id: int | None = None):
        return [{"uid": str(user_id), "value": 150}]

    remove_users = AsyncMock()
    monkeypatch.setattr(record_usages, "get_users_stats", fake_get_users_stats)
    monkeypatch.setattr(record_usages.usage_settings, "disable_recording_node_usage", True)
    monkeypatch.setattr("app.operation.admin_sync.sync_remove_users", remove_users)

    await record_usages.record_user_usages()

    async with session_factory() as session:
        admin_status = await session.execute(select(Admin.status).where(Admin.id == admin_id))
        assert admin_status.scalar_one() == AdminStatus.limited

    remove_users.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_user_stats_batched_skips_missing_users(session_factory):
    async with session_factory() as session:
        admin = Admin(username="admin", hashed_password="secret", role_id=3)
        session.add(admin)
        await session.flush()

        user = User(username="user", admin_id=admin.id, proxy_settings=ProxyTable().dict(no_obj=True))
        node = Node(
            name="node-1",
            address="10.0.0.1",
            port=1000,
            api_port=1001,
            server_ca="ca1",
            api_key="key1",
            core_config_id=None,
        )
        session.add_all([user, node])
        await session.flush()
        user_id, node_id = user.id, node.id
        missing_user_id = user_id + 10_000
        await session.commit()

    await record_usages.record_user_stats_batched(
        {
            node_id: [
                {"uid": str(user_id), "value": 100},
                {"uid": str(missing_user_id), "value": 200},
            ]
        },
        {node_id: 1},
    )

    async with session_factory() as session:
        rows = await session.execute(select(NodeUserUsage.user_id, NodeUserUsage.used_traffic))
        records = rows.all()

    assert records == [(user_id, 100)]


@pytest.mark.asyncio
async def test_record_user_stats_batched_chunks_mysql_batches(monkeypatch: pytest.MonkeyPatch):
    executed_param_sizes = []

    async def fake_get_dialect():
        return "mysql"

    async def fake_safe_execute(stmt, params=None, max_retries=5):
        executed_param_sizes.append(len(params))

    monkeypatch.setattr(record_usages, "get_dialect", fake_get_dialect)
    monkeypatch.setattr(record_usages, "safe_execute", fake_safe_execute)
    monkeypatch.setattr(record_usages, "_get_time_bucket", lambda: None)

    params = [{"uid": str(index + 1), "value": 1} for index in range(2_501)]

    await record_usages.record_user_stats_batched({1: params}, {1: 1})

    assert executed_param_sizes == [4_000, 4_000, 2_004]


@pytest.mark.asyncio
async def test_record_user_usages_returns_when_no_usage(monkeypatch: pytest.MonkeyPatch, session_factory):
    async with session_factory() as session:
        admin = Admin(username="admin", hashed_password="secret", role_id=3)
        session.add(admin)
        await session.flush()
        admin_id = admin.id

        user = User(username="user", admin_id=admin_id, proxy_settings=ProxyTable().dict(no_obj=True))
        node = Node(
            name="node-1",
            address="10.0.0.1",
            port=1000,
            api_port=1001,
            server_ca="ca1",
            api_key="key1",
            core_config_id=None,
        )
        session.add_all([user, node])
        await session.flush()
        user_id, node_id = user.id, node.id
        await session.commit()

    nodes = [(node_id, DummyNode(node_id))]
    monkeypatch.setattr(record_usages.node_manager, "get_healthy_nodes", AsyncMock(return_value=nodes))

    async def fake_get_users_stats(_: DummyNode, node_id: int | None = None):
        return []

    monkeypatch.setattr(record_usages, "get_users_stats", fake_get_users_stats)
    monkeypatch.setattr(record_usages.usage_settings, "disable_recording_node_usage", False)

    await record_usages.record_user_usages()

    async with session_factory() as session:
        user_total = await session.execute(select(User.used_traffic).where(User.id == user_id))
        assert user_total.scalar_one() == 0

        admin_total = await session.execute(select(Admin.used_traffic).where(Admin.id == admin_id))
        assert admin_total.scalar_one() == 0

        node_user_usage = await session.execute(select(NodeUserUsage.id))
        assert node_user_usage.first() is None


@pytest.mark.asyncio
async def test_record_node_usages_updates_totals(monkeypatch: pytest.MonkeyPatch, session_factory):
    async with session_factory() as session:
        node_one = Node(
            name="node-1",
            address="10.0.0.1",
            port=1000,
            api_port=1001,
            server_ca="ca1",
            api_key="key1",
            core_config_id=None,
        )
        node_two = Node(
            name="node-2",
            address="10.0.0.2",
            port=1001,
            api_port=1002,
            server_ca="ca2",
            api_key="key2",
            core_config_id=None,
        )
        system = System(uplink=0, downlink=0)
        session.add_all([node_one, node_two, system])
        await session.flush()
        node_one_id, node_two_id, system_id = node_one.id, node_two.id, system.id
        await session.commit()

    nodes = [(node_one_id, DummyNode(node_one_id)), (node_two_id, DummyNode(node_two_id))]
    monkeypatch.setattr(record_usages.node_manager, "get_healthy_nodes", AsyncMock(return_value=nodes))

    stats_map = {
        node_one_id: [{"up": 10, "down": 4}, {"up": 0, "down": 3}],
        node_two_id: [{"up": 1, "down": 1}],
    }

    async def fake_get_outbounds_stats(node: DummyNode, node_id: int | None = None):
        return stats_map[node.node_id]

    monkeypatch.setattr(record_usages, "get_outbounds_stats", fake_get_outbounds_stats)
    monkeypatch.setattr(record_usages.usage_settings, "disable_recording_node_usage", False)

    await record_usages.record_node_usages()

    async with session_factory() as session:
        nodes_result = await session.execute(select(Node.id, Node.uplink, Node.downlink))
        node_totals = {row.id: (row.uplink, row.downlink) for row in nodes_result.all()}
        assert node_totals[node_one_id][0] > node_totals[node_two_id][0]
        assert node_totals[node_two_id][1] > 0

        node_usage_rows = await session.execute(select(NodeUsage.node_id, NodeUsage.uplink, NodeUsage.downlink))
        node_usage_totals = {row.node_id: (row.uplink, row.downlink) for row in node_usage_rows.all()}
        assert set(node_usage_totals.keys()) == {node_one_id, node_two_id}

        assert node_usage_totals[node_one_id][0] >= node_usage_totals[node_two_id][0]
        assert node_usage_totals[node_one_id][1] > 0
        assert node_usage_totals[node_two_id][1] > 0

        system_totals = await session.execute(select(System.uplink, System.downlink).where(System.id == system_id))
        system_row = system_totals.one()
        assert system_row.uplink == sum(values[0] for values in node_totals.values())
        assert system_row.downlink == sum(values[1] for values in node_totals.values())


@pytest.mark.asyncio
async def test_record_node_usages_returns_when_totals_zero(monkeypatch: pytest.MonkeyPatch, session_factory):
    async with session_factory() as session:
        node = Node(
            name="node-1",
            address="10.0.0.1",
            port=1000,
            api_port=1001,
            server_ca="ca1",
            api_key="key1",
            core_config_id=None,
        )
        system = System(uplink=0, downlink=0)
        session.add_all([node, system])
        await session.flush()
        node_id, system_id = node.id, system.id
        await session.commit()

    nodes = [(node_id, DummyNode(node_id))]
    monkeypatch.setattr(record_usages.node_manager, "get_healthy_nodes", AsyncMock(return_value=nodes))

    async def fake_get_outbounds_stats(_: DummyNode, node_id: int | None = None):
        return [{"up": 0, "down": 0}]

    monkeypatch.setattr(record_usages, "get_outbounds_stats", fake_get_outbounds_stats)

    await record_usages.record_node_usages()

    async with session_factory() as session:
        node_row = await session.execute(select(Node.uplink, Node.downlink).where(Node.id == node_id))
        node_totals = node_row.one()
        assert node_totals.uplink == 0
        assert node_totals.downlink == 0

        system_row = await session.execute(select(System.uplink, System.downlink).where(System.id == system_id))
        system_totals = system_row.one()
        assert system_totals.uplink == 0
        assert system_totals.downlink == 0

        node_usage_rows = await session.execute(select(NodeUsage.id))
        assert node_usage_rows.first() is None


class _DeadlockOrig(Exception):
    def __init__(self):
        super().__init__(1213, "Deadlock found when trying to get lock; try restarting transaction")


class _FakeBeginConn:
    def __init__(self, execute):
        self._execute = execute

    async def execute(self, stmt, params=None):
        return await self._execute(stmt, params)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, execute):
        self._execute = execute

    def execution_options(self, **_kwargs):
        return self

    def begin(self):
        return _FakeBeginConn(self._execute)


@pytest.mark.asyncio
async def test_safe_execute_retries_mysql_deadlock(monkeypatch: pytest.MonkeyPatch):
    attempts = {"n": 0}

    async def flaky_execute(_stmt, _params=None):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OperationalError("stmt", {}, _DeadlockOrig())

    monkeypatch.setattr(record_usages, "engine", _FakeEngine(flaky_execute))
    monkeypatch.setattr(record_usages, "get_dialect", AsyncMock(return_value="mysql"))
    monkeypatch.setattr(record_usages.asyncio, "sleep", AsyncMock())

    await record_usages.safe_execute("stmt", [{"uid": 1}])

    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_safe_execute_raises_after_deadlock_retries(monkeypatch: pytest.MonkeyPatch):
    async def always_deadlock(_stmt, _params=None):
        raise OperationalError("stmt", {}, _DeadlockOrig())

    monkeypatch.setattr(record_usages, "engine", _FakeEngine(always_deadlock))
    monkeypatch.setattr(record_usages, "get_dialect", AsyncMock(return_value="mysql"))
    monkeypatch.setattr(record_usages.asyncio, "sleep", AsyncMock())

    with pytest.raises(OperationalError):
        await record_usages.safe_execute("stmt", [{"uid": 1}], max_retries=3)


@pytest.fixture(autouse=True)
def _reset_usage_job_state():
    record_usages._usage_coefficient_cache.clear()
    record_usages._user_usage_running = False
    record_usages._node_usage_running = False
    yield
    record_usages._usage_coefficient_cache.clear()
    record_usages._user_usage_running = False
    record_usages._node_usage_running = False


@pytest.mark.asyncio
async def test_record_user_usages_skips_when_already_running(monkeypatch: pytest.MonkeyPatch, caplog):
    impl = AsyncMock()
    monkeypatch.setattr(record_usages, "_record_user_usages_impl", impl)
    record_usages._user_usage_running = True
    caplog.set_level(logging.WARNING)
    await record_usages.record_user_usages()

    impl.assert_not_awaited()
    assert "JOB_RECORD_USER_USAGES_INTERVAL" in caplog.text
    assert "UVICORN_WORKERS" in caplog.text


@pytest.mark.asyncio
async def test_record_node_usages_skips_when_already_running(monkeypatch: pytest.MonkeyPatch, caplog):
    impl = AsyncMock()
    monkeypatch.setattr(record_usages, "_record_node_usages_impl", impl)
    record_usages._node_usage_running = True
    caplog.set_level(logging.WARNING)
    await record_usages.record_node_usages()

    impl.assert_not_awaited()
    assert "JOB_RECORD_NODE_USAGES_INTERVAL" in caplog.text
    assert "UVICORN_WORKERS" in caplog.text


@pytest.mark.asyncio
async def test_record_user_usages_does_not_apply_global_timeout(monkeypatch: pytest.MonkeyPatch):
    impl = AsyncMock()
    wait_for = AsyncMock(side_effect=AssertionError("wait_for should not run"))
    monkeypatch.setattr(record_usages, "_record_user_usages_impl", impl)
    monkeypatch.setattr(record_usages.asyncio, "wait_for", wait_for)

    await record_usages.record_user_usages()

    impl.assert_awaited_once()
    wait_for.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_user_usages_warns_when_slower_than_interval(monkeypatch: pytest.MonkeyPatch, caplog):
    clock = {"t": 0.0}

    async def impl():
        clock["t"] = 15.0

    monkeypatch.setattr(record_usages.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(record_usages, "_record_user_usages_impl", impl)
    monkeypatch.setattr(record_usages.job_settings, "record_user_usages_interval", 10)
    caplog.set_level(logging.WARNING)

    await record_usages.record_user_usages()

    assert "exceeds the 10s interval" in caplog.text
    assert "UVICORN_WORKERS" in caplog.text


@pytest.mark.asyncio
async def test_usage_coefficient_is_cached_across_collects(monkeypatch: pytest.MonkeyPatch):
    node = DummyNode(1, usage_coefficient=2)
    extra_calls = {"n": 0}
    original_get_extra = node.get_extra

    async def counting_get_extra():
        extra_calls["n"] += 1
        return await original_get_extra()

    node.get_extra = counting_get_extra
    monkeypatch.setattr(record_usages, "get_users_stats", AsyncMock(return_value=[]))

    first = await record_usages._collect_node_user_usage(node, 1)
    second = await record_usages._collect_node_user_usage(node, 1)

    assert extra_calls["n"] == 1
    assert first[1] == second[1] == 2.0


@pytest.mark.asyncio
async def test_compact_old_usages_preserves_totals_and_is_repeatable(session_factory):
    day = datetime(2026, 9, 1, tzinfo=UTC)
    now = datetime(2026, 9, 23, tzinfo=UTC)
    async with session_factory() as session:
        admin = Admin(username="rollup-admin", hashed_password="secret", role_id=3)
        session.add(admin)
        await session.flush()
        user = User(username="rollup-user", admin_id=admin.id, proxy_settings=ProxyTable().dict(no_obj=True))
        session.add(user)
        await session.flush()
        admin_id = admin.id
        user_id = user.id
        session.add_all(
            [
                NodeUserUsage(user_id=user_id, node_id=None, created_at=day, used_traffic=10),
                NodeUserUsage(user_id=user_id, node_id=None, created_at=day + timedelta(hours=1), used_traffic=20),
                NodeUserUsage(user_id=user_id, node_id=None, created_at=day + timedelta(hours=23), used_traffic=30),
                NodeUserUsage(user_id=user_id, node_id=None, created_at=now, used_traffic=40),
                NodeUsage(node_id=None, created_at=day, uplink=1, downlink=2),
                NodeUsage(node_id=None, created_at=day + timedelta(hours=2), uplink=3, downlink=4),
            ]
        )
        await session.commit()

    await compact_usages.compact_old_usages(now)
    await compact_usages.compact_old_usages(now)
    async with session_factory() as session:
        users = (await session.execute(select(NodeUserUsage).order_by(NodeUserUsage.created_at))).scalars().all()
        nodes = (await session.execute(select(NodeUsage))).scalars().all()
        assert [(row.used_traffic, row.is_daily) for row in users] == [(60, True), (40, False)]
        assert [(row.uplink, row.downlink, row.is_daily) for row in nodes] == [(4, 6, True)]
        full = await get_user_usages(session, user_id, day, day + timedelta(days=1), Period.day)
        partial = await get_user_usages(session, user_id, day, day + timedelta(hours=12), Period.hour)
        assert sum(point.total_traffic for points in full.stats.values() for point in points) == 60
        assert sum(point.total_traffic for points in partial.stats.values() for point in points) == 60
        tehran = timezone(timedelta(hours=3, minutes=30))
        local_start = day.astimezone(tehran).replace(hour=0, minute=0)
        local_end = local_start + timedelta(days=1)
        local = await get_user_usages(session, user_id, local_start, local_end, Period.day)
        admin_usage = await get_admin_usages(session, admin_id, day, day + timedelta(days=1), Period.day)
        all_usage = await get_all_users_usages(session, None, day, day + timedelta(days=1), Period.day)
        node_usage = await get_nodes_usage(session, day, day + timedelta(days=1), Period.day)
        for usage in (local, admin_usage, all_usage):
            assert sum(point.total_traffic for points in usage.stats.values() for point in points) == 60
        assert sum(point.uplink for points in node_usage.stats.values() for point in points) == 4
        assert sum(point.downlink for points in node_usage.stats.values() for point in points) == 6

        # A late import into an already compacted day is folded in once.
        session.add(NodeUserUsage(user_id=user_id, node_id=None, created_at=day + timedelta(hours=5), used_traffic=7))
        await session.commit()

    await compact_usages.compact_old_usages(now)
    async with session_factory() as session:
        old = (
            (await session.execute(select(NodeUserUsage).where(NodeUserUsage.created_at < day + timedelta(days=1))))
            .scalars()
            .all()
        )
        assert len(old) == 1
        assert old[0].used_traffic == 67
        assert old[0].is_daily is True


@pytest.mark.asyncio
async def test_compaction_handles_legacy_sqlite_timestamp_formats(session_factory):
    """Older SQLite rows can have timestamps without fractional seconds."""
    async with session_factory() as session:
        admin = Admin(username="legacy-rollup-admin", hashed_password="secret", role_id=3)
        session.add(admin)
        await session.flush()
        user = User(username="legacy-rollup-user", admin_id=admin.id, proxy_settings=ProxyTable().dict(no_obj=True))
        session.add(user)
        await session.flush()
        user_id = user.id
        for stamp, traffic in (
            ("2026-09-01 00:00:00", 10),
            ("2026-09-01 10:00:00", 20),
            ("2026-09-02 00:00:00", 40),
        ):
            await session.execute(
                text(
                    "INSERT INTO node_user_usages (created_at, user_id, node_id, used_traffic) "
                    "VALUES (:created_at, :user_id, NULL, :traffic)"
                ),
                {"created_at": stamp, "user_id": user_id, "traffic": traffic},
            )
        await session.commit()

    await compact_usages.compact_old_usages(datetime(2026, 9, 9, 12, tzinfo=UTC))
    async with session_factory() as session:
        rows = (await session.execute(select(NodeUserUsage).order_by(NodeUserUsage.created_at))).scalars().all()
        assert [(row.used_traffic, row.is_daily) for row in rows] == [(30, True), (40, False)]
