from __future__ import annotations

import logging
import os
import random
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import base
from app.db.crud.node import remove_node
from app.db.models import Admin, AdminRole, AdminStatus, Node, NodeUsage, NodeUserUsage, System, User
from app.jobs import record_usages
from app.models.proxy import ProxyTable
from app.operation import admin_sync
from config import database_settings


class DummyNode:
    def __init__(self, node_id: int, usage_coefficient: int = 1):
        self.node_id = node_id
        self._usage_coefficient = usage_coefficient

    async def get_extra(self) -> dict[str, Any]:
        return {"usage_coefficient": self._usage_coefficient}


@pytest.fixture(autouse=True)
def reset_user_usage_history_buffer():
    """Keep process-local history buffering isolated between tests."""
    record_usages._pending_user_usage_history.clear()
    record_usages._user_usage_history_last_flush = None
    yield
    record_usages._pending_user_usage_history.clear()
    record_usages._user_usage_history_last_flush = None


def test_prepare_node_user_usage_params_aggregates_nonzero_deltas():
    bucket = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)

    params = record_usages._prepare_node_user_usage_params(
        {
            7: [
                {"uid": "11", "value": 5},
                {"uid": "11", "value": 3},
                {"uid": "12", "value": 0},
                {"uid": "13", "value": -2},
            ]
        },
        {7: 2},
        bucket,
    )

    assert params == [
        {"uid": 11, "value": 16, "node_id": 7, "created_at": bucket},
        {"uid": 13, "value": -4, "node_id": 7, "created_at": bucket},
    ]


@pytest.mark.asyncio
async def test_postgres_history_writes_the_first_sample_immediately(monkeypatch: pytest.MonkeyPatch):
    bucket = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)
    write_params = AsyncMock()

    monkeypatch.setattr(record_usages, "get_dialect", AsyncMock(return_value="postgresql"))
    monkeypatch.setattr(record_usages, "_get_time_bucket", lambda: bucket)
    monkeypatch.setattr(record_usages, "_write_node_user_usage_params", write_params)
    monkeypatch.setattr(record_usages, "_monotonic_now", lambda: 100.0)

    await record_usages.record_user_stats({7: [{"uid": "11", "value": 5}]}, {7: 1})

    write_params.assert_awaited_once_with(
        "postgresql",
        [{"uid": 11, "value": 5, "node_id": 7, "created_at": bucket}],
    )
    assert not record_usages._pending_user_usage_history
    assert record_usages._user_usage_history_last_flush == 100.0


@pytest.mark.asyncio
async def test_postgres_history_coalesces_until_flush_interval(monkeypatch: pytest.MonkeyPatch):
    # Steady state: the first sample was already written, so later samples are coalesced
    record_usages._user_usage_history_last_flush = 100.0
    bucket = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)
    write_params = AsyncMock()
    monotonic_values = iter([100.0, 110.0, 161.0])

    monkeypatch.setattr(record_usages, "get_dialect", AsyncMock(return_value="postgresql"))
    monkeypatch.setattr(record_usages, "_get_time_bucket", lambda: bucket)
    monkeypatch.setattr(record_usages, "_write_node_user_usage_params", write_params)
    monkeypatch.setattr(record_usages, "_monotonic_now", lambda: next(monotonic_values))
    monkeypatch.setattr(record_usages.usage_settings, "user_usage_history_flush_interval", 60)

    await record_usages.record_user_stats({7: [{"uid": "11", "value": 5}]}, {7: 1})
    await record_usages.record_user_stats({7: [{"uid": "11", "value": 7}]}, {7: 1})
    await record_usages.record_user_stats({7: [{"uid": "11", "value": 9}]}, {7: 1})

    write_params.assert_awaited_once_with(
        "postgresql",
        [{"uid": 11, "value": 21, "node_id": 7, "created_at": bucket}],
    )
    assert not record_usages._pending_user_usage_history


@pytest.mark.asyncio
async def test_postgres_history_flushes_old_bucket_before_rollover(monkeypatch: pytest.MonkeyPatch):
    # Steady state: the first sample was already written, so later samples are coalesced
    record_usages._user_usage_history_last_flush = 100.0
    old_bucket = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)
    new_bucket = old_bucket + timedelta(minutes=10)
    buckets = iter([old_bucket, old_bucket, new_bucket])
    write_params = AsyncMock()

    monkeypatch.setattr(record_usages, "get_dialect", AsyncMock(return_value="postgresql"))
    monkeypatch.setattr(record_usages, "_get_time_bucket", lambda: next(buckets))
    monkeypatch.setattr(record_usages, "_write_node_user_usage_params", write_params)
    monkeypatch.setattr(record_usages, "_monotonic_now", lambda: 100.0)
    monkeypatch.setattr(record_usages.usage_settings, "user_usage_history_flush_interval", 60)

    await record_usages.record_user_stats({7: [{"uid": "11", "value": 5}]}, {7: 1})
    await record_usages.record_user_stats({7: [{"uid": "11", "value": 7}]}, {7: 1})
    await record_usages.record_user_stats({7: [{"uid": "11", "value": 9}]}, {7: 1})

    write_params.assert_awaited_once_with(
        "postgresql",
        [{"uid": 11, "value": 12, "node_id": 7, "created_at": old_bucket}],
    )
    assert record_usages._pending_user_usage_history == {(new_bucket, 11, 7): 9}


@pytest.mark.asyncio
async def test_postgres_history_retains_failed_flush_for_retry(monkeypatch: pytest.MonkeyPatch):
    # Steady state: the first sample was already written, so later samples are coalesced
    record_usages._user_usage_history_last_flush = 100.0
    bucket = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)
    write_params = AsyncMock(side_effect=[RuntimeError("database unavailable"), None])
    monotonic_values = iter([100.0, 160.0])

    monkeypatch.setattr(record_usages, "get_dialect", AsyncMock(return_value="postgresql"))
    monkeypatch.setattr(record_usages, "_get_time_bucket", lambda: bucket)
    monkeypatch.setattr(record_usages, "_write_node_user_usage_params", write_params)
    monkeypatch.setattr(record_usages, "_monotonic_now", lambda: next(monotonic_values))

    await record_usages.record_user_stats({7: [{"uid": "11", "value": 5}]}, {7: 1})

    with pytest.raises(RuntimeError, match="database unavailable"):
        await record_usages.record_user_stats({7: [{"uid": "11", "value": 7}]}, {7: 1})

    assert record_usages._pending_user_usage_history == {(bucket, 11, 7): 12}

    flushed_rows = await record_usages.flush_user_usage_history_if_due(161.0)

    assert flushed_rows == 1
    assert write_params.await_args_list[1].args == (
        "postgresql",
        [{"uid": 11, "value": 12, "node_id": 7, "created_at": bucket}],
    )
    assert not record_usages._pending_user_usage_history


def _foreign_key_error() -> IntegrityError:
    return IntegrityError("INSERT INTO node_user_usages", {}, Exception("violates foreign key constraint"))


@pytest.mark.asyncio
async def test_history_write_drops_a_batch_the_database_rejects(monkeypatch: pytest.MonkeyPatch, caplog):
    bucket = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)
    executed = []

    async def fake_safe_execute(stmt, params=None, max_retries=5):
        executed.append(params)
        if len(executed) == 1:
            raise _foreign_key_error()

    monkeypatch.setattr(record_usages, "safe_execute", fake_safe_execute)
    caplog.set_level(logging.ERROR)
    rows = [{"uid": index + 1, "value": 1, "node_id": 7, "created_at": bucket} for index in range(2_000)]

    await record_usages._write_node_user_usage_params("mysql", rows)

    # The rejected batch is dropped with a log line and the next batch is still written
    assert len(executed) == 2
    assert "Dropped 1000 node user usage history rows" in caplog.text


@pytest.mark.asyncio
async def test_postgres_history_drops_rows_the_database_rejects(monkeypatch: pytest.MonkeyPatch, caplog):
    # Steady state: the first sample was already written, so later samples are coalesced
    record_usages._user_usage_history_last_flush = 100.0
    bucket = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)
    executed = []
    monotonic_values = iter([100.0, 161.0, 222.0])

    async def fake_safe_execute(stmt, params=None, max_retries=5):
        executed.append(params)
        if len(executed) == 1:
            raise _foreign_key_error()

    monkeypatch.setattr(record_usages, "get_dialect", AsyncMock(return_value="postgresql"))
    monkeypatch.setattr(record_usages, "_get_time_bucket", lambda: bucket)
    monkeypatch.setattr(record_usages, "safe_execute", fake_safe_execute)
    monkeypatch.setattr(record_usages, "_monotonic_now", lambda: next(monotonic_values))
    monkeypatch.setattr(record_usages.usage_settings, "user_usage_history_flush_interval", 60)
    caplog.set_level(logging.ERROR)

    await record_usages.record_user_stats({7: [{"uid": "11", "value": 5}]}, {7: 1})
    # This flush is rejected: retrying the same rows could never succeed, so they are dropped
    await record_usages.record_user_stats({7: [{"uid": "11", "value": 7}]}, {7: 1})
    assert not record_usages._pending_user_usage_history
    assert "Dropped 1 node user usage history rows" in caplog.text

    await record_usages.record_user_stats({7: [{"uid": "11", "value": 9}]}, {7: 1})

    assert len(executed) == 2
    assert executed[1]["traffic_values"] == [9]
    assert not record_usages._pending_user_usage_history


@pytest.mark.asyncio
async def test_postgres_history_caps_buffered_buckets_after_failed_flushes(monkeypatch: pytest.MonkeyPatch, caplog):
    # Steady state: the first sample was already written, so later samples are coalesced
    record_usages._user_usage_history_last_flush = 100.0
    first_bucket = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)
    buckets = [first_bucket + timedelta(minutes=10 * index) for index in range(9)]
    bucket_values = iter(buckets)

    async def failing_safe_execute(stmt, params=None, max_retries=5):
        raise OperationalError("INSERT INTO node_user_usages", {}, Exception("connection lost"))

    monkeypatch.setattr(record_usages, "get_dialect", AsyncMock(return_value="postgresql"))
    monkeypatch.setattr(record_usages, "_get_time_bucket", lambda: next(bucket_values))
    monkeypatch.setattr(record_usages, "safe_execute", failing_safe_execute)
    monkeypatch.setattr(record_usages, "_monotonic_now", lambda: 100.0)
    monkeypatch.setattr(record_usages.usage_settings, "user_usage_history_flush_interval", 60)
    caplog.set_level(logging.ERROR)

    await record_usages.record_user_stats({7: [{"uid": "11", "value": 5}]}, {7: 1})
    for _ in buckets[1:]:
        # Every bucket rollover tries to flush the older buckets and fails
        with pytest.raises(OperationalError):
            await record_usages.record_user_stats({7: [{"uid": "11", "value": 5}]}, {7: 1})

    # Failed flushes keep at most an hour (6 buckets) of older history next to the current bucket
    pending_buckets = sorted({key[0] for key in record_usages._pending_user_usage_history})
    assert pending_buckets == buckets[2:]
    assert "Dropped 1 buffered node user usage history rows" in caplog.text


@pytest.mark.asyncio
async def test_due_history_flushes_without_a_new_usage_sample(monkeypatch: pytest.MonkeyPatch):
    bucket = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)
    write_params = AsyncMock()
    record_usages._pending_user_usage_history[(bucket, 11, 7)] = 5
    record_usages._user_usage_history_last_flush = 100.0

    monkeypatch.setattr(record_usages, "_write_node_user_usage_params", write_params)
    monkeypatch.setattr(record_usages.usage_settings, "user_usage_history_flush_interval", 60)

    early_rows = await record_usages.flush_user_usage_history_if_due(159.0)
    flushed_rows = await record_usages.flush_user_usage_history_if_due(160.0)

    assert early_rows == 0
    assert flushed_rows == 1
    write_params.assert_awaited_once_with(
        "postgresql",
        [{"uid": 11, "value": 5, "node_id": 7, "created_at": bucket}],
    )
    assert not record_usages._pending_user_usage_history


@pytest.mark.asyncio
async def test_postgres_history_omits_cross_cycle_net_zero_values(monkeypatch: pytest.MonkeyPatch):
    # Steady state: the first sample was already written, so later samples are coalesced
    record_usages._user_usage_history_last_flush = 100.0
    bucket = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)
    write_params = AsyncMock()
    monotonic_values = iter([100.0, 110.0])

    monkeypatch.setattr(record_usages, "get_dialect", AsyncMock(return_value="postgresql"))
    monkeypatch.setattr(record_usages, "_get_time_bucket", lambda: bucket)
    monkeypatch.setattr(record_usages, "_write_node_user_usage_params", write_params)
    monkeypatch.setattr(record_usages, "_monotonic_now", lambda: next(monotonic_values))
    monkeypatch.setattr(record_usages.usage_settings, "user_usage_history_flush_interval", 60)

    await record_usages.record_user_stats({7: [{"uid": "11", "value": 5}]}, {7: 1})
    await record_usages.record_user_stats({7: [{"uid": "11", "value": -5}]}, {7: 1})
    flushed_rows = await record_usages.flush_user_usage_history_if_due(160.0)

    assert flushed_rows == 0
    write_params.assert_not_awaited()
    assert not record_usages._pending_user_usage_history


@pytest.mark.asyncio
async def test_non_postgres_history_keeps_immediate_path(monkeypatch: pytest.MonkeyPatch):
    immediate_write = AsyncMock()
    node_params = {7: [{"uid": "11", "value": 5}]}
    coefficients = {7: 1}

    monkeypatch.setattr(record_usages, "get_dialect", AsyncMock(return_value="sqlite"))
    monkeypatch.setattr(record_usages, "record_user_stats_batched", immediate_write)

    await record_usages.record_user_stats(node_params, coefficients)

    immediate_write.assert_awaited_once_with(node_params, coefficients)


@pytest.mark.asyncio
async def test_shutdown_flushes_pending_postgres_history(monkeypatch: pytest.MonkeyPatch):
    bucket = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)
    write_params = AsyncMock()
    record_usages._pending_user_usage_history[(bucket, 11, 7)] = 5

    monkeypatch.setattr(record_usages, "_write_node_user_usage_params", write_params)
    monkeypatch.setattr(record_usages, "_monotonic_now", lambda: 120.0)

    await record_usages._flush_user_usage_history_on_shutdown()

    write_params.assert_awaited_once_with(
        "postgresql",
        [{"uid": 11, "value": 5, "node_id": 7, "created_at": bucket}],
    )
    assert not record_usages._pending_user_usage_history


def test_postgres_user_traffic_update_uses_one_unnest_statement():
    usage_params = [
        {"uid": 1, "value": 10},
        {"uid": 2, "value": 20},
        {"uid": 1, "value": 30},
    ]

    stmt, params = record_usages.build_user_traffic_update("postgresql", usage_params)
    sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert "UPDATE users" in sql
    assert "FROM unnest" in sql
    assert "online_at" not in sql
    assert params == {"uids": [1, 2], "traffic_values": [40, 20]}


def test_mysql_user_traffic_update_uses_one_case_statement():
    usage_params = [
        {"uid": 1, "value": 10},
        {"uid": 2, "value": 20},
        {"uid": 1, "value": 30},
    ]

    stmt, params = record_usages.build_user_traffic_update("mysql", usage_params)
    compiled = stmt.compile(dialect=mysql.dialect(), compile_kwargs={"render_postcompile": True})
    sql = str(compiled)

    assert "UPDATE users" in sql
    assert "CASE users.id WHEN" in sql
    assert params is None
    # Repeated users are summed: a CASE only uses the first matching WHEN
    assert list(compiled.params.values()) == [1, 40, 2, 20, 1, 2]


def _get_test_database_url(tmp_path) -> str:
    test_from = os.getenv("TEST_FROM", "local").lower()
    if test_from == "local":
        # A file database, not :memory: with one shared StaticPool connection: the usage
        # jobs write from concurrent tasks, and on a shared connection one task's
        # ROLLBACK or COMMIT ends the other tasks' transactions
        return f"sqlite+aiosqlite:///{tmp_path / 'record_usages.db'}"
    return database_settings.url


@pytest.fixture
async def session_factory(monkeypatch: pytest.MonkeyPatch, tmp_path):
    database_url = _get_test_database_url(tmp_path)
    is_sqlite = database_url.startswith("sqlite")

    engine_kwargs = {"poolclass": NullPool}
    connect_args = {}
    if is_sqlite:
        connect_args["check_same_thread"] = False

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
    monkeypatch.setattr(admin_sync, "GetDB", TestGetDB)

    yield session_factory

    # With TEST_FROM set this is the shared CI database, which later test files use too: leave every table, empty
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.drop_all)
        await conn.run_sync(base.Base.metadata.create_all)
    await engine.dispose()
    if needs_json_default_fix and proxy_column is not None:
        proxy_column.server_default = proxy_default


@pytest.mark.asyncio
async def test_touch_users_online_at_throttles_indexed_timestamp_writes(session_factory):
    async with session_factory() as session:
        user = User(username="online-write-throttle")
        session.add(user)
        await session.commit()
        user_id = user.id

    # Whole seconds: MySQL stores DATETIME without fractions and rounds them, which would
    # move the stored time past the 60 second cutoff the test checks
    first_seen = datetime.now(UTC).replace(microsecond=0)
    await record_usages.touch_users_online_at([user_id], first_seen)

    async def get_online_at():
        async with session_factory() as session:
            return (await session.execute(select(User.online_at).where(User.id == user_id))).scalar_one()

    initial_online_at = await get_online_at()
    await record_usages.touch_users_online_at([user_id], first_seen + timedelta(seconds=30))
    throttled_online_at = await get_online_at()
    await record_usages.touch_users_online_at([user_id], first_seen + timedelta(seconds=60))
    refreshed_online_at = await get_online_at()

    assert initial_online_at == throttled_online_at
    assert refreshed_online_at > throttled_online_at


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
        node_zero = Node(
            name="node-zero",
            address="10.0.0.3",
            port=1003,
            api_port=1004,
            server_ca="ca3",
            api_key="key3",
            core_config_id=None,
        )
        session.add_all([node_one, node_two, node_zero])
        await session.flush()
        node_one_id, node_two_id, node_zero_id = node_one.id, node_two.id, node_zero.id
        await session.commit()

    nodes = [
        (node_one_id, DummyNode(node_one_id, usage_coefficient=2)),
        (node_two_id, DummyNode(node_two_id, usage_coefficient=1)),
        (node_zero_id, DummyNode(node_zero_id, usage_coefficient=0)),
    ]
    monkeypatch.setattr(record_usages.node_manager, "get_healthy_nodes", AsyncMock(return_value=nodes))

    stats_map = {
        node_one_id: [{"uid": str(user_one_id), "value": 100}, {"uid": str(user_two_id), "value": 50}],
        node_two_id: [{"uid": str(user_one_id), "value": 75}],
        node_zero_id: [{"uid": str(user_one_id), "value": 500}],
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

        assert user_totals[user_one_id][0] == 275
        assert user_totals[user_two_id][0] == 100
        assert all(total > 0 for total, _ in user_totals.values())
        assert all(online_at is not None for _, online_at in user_totals.values())

        admin_total = await session.execute(select(Admin.used_traffic).where(Admin.id == admin_id))
        admin_used = admin_total.scalar_one()
        assert admin_used == 375

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
async def test_usage_cycles_match_a_reference_model(monkeypatch: pytest.MonkeyPatch, session_factory):
    """Pin what two usage cycles write (totals, online users, history, node usage) across the batch sizes."""
    rng = random.Random(946)
    bucket = datetime(2026, 8, 14, 18, 30, tzinfo=UTC)
    async with session_factory() as session:
        admins = [Admin(username=f"admin-{index}", hashed_password="secret", role_id=3) for index in range(2)]
        session.add_all(admins)
        await session.flush()
        users = [
            User(
                username=f"user-{index}",
                admin_id=admins[index % 3].id if index % 3 < 2 else None,
                proxy_settings=ProxyTable().dict(no_obj=True),
            )
            for index in range(1_200)
        ]
        nodes = [
            Node(
                name=f"node-{index}",
                address=f"10.0.0.{index}",
                port=1000 + index,
                api_port=2000 + index,
                server_ca="ca",
                api_key=f"key{index}",
                core_config_id=None,
            )
            for index in range(3)
        ]
        system = System(uplink=0, downlink=0)
        session.add_all([*users, *nodes, system])
        await session.flush()
        user_admin = {user.id: user.admin_id for user in users}
        admin_ids = [admin.id for admin in admins]
        node_ids = [node.id for node in nodes]
        await session.commit()

    user_ids = sorted(user_admin)
    missing_user_id = user_ids[-1] + 10_000
    coefficients = dict(zip(node_ids, (1, 1.5, 0)))
    users_per_node = dict(zip(node_ids, (1_100, 900, 300)))
    cycles = [
        {
            node_id: [{"uid": uid, "value": rng.randint(1, 10**9)} for uid in rng.sample(user_ids, count)]
            + [{"uid": missing_user_id, "value": 7}]
            for node_id, count in users_per_node.items()
        }
        for _ in range(2)
    ]
    outbound_cycles = [
        {node_id: [{"up": rng.randint(1, 10**9), "down": rng.randint(1, 10**9)}] for node_id in node_ids}
        for _ in range(2)
    ]
    current = {"cycle": 0}

    async def fake_get_users_stats(node: DummyNode, node_id: int | None = None):
        return cycles[current["cycle"]][node.node_id]

    async def fake_get_outbounds_stats(node: DummyNode, node_id: int | None = None):
        return outbound_cycles[current["cycle"]][node.node_id]

    nodes_by_id = [(node_id, DummyNode(node_id, usage_coefficient=coefficients[node_id])) for node_id in node_ids]
    monkeypatch.setattr(record_usages.node_manager, "get_healthy_nodes", AsyncMock(return_value=nodes_by_id))
    monkeypatch.setattr(record_usages, "get_users_stats", fake_get_users_stats)
    monkeypatch.setattr(record_usages, "get_outbounds_stats", fake_get_outbounds_stats)
    monkeypatch.setattr(record_usages, "_get_time_bucket", lambda: bucket)
    monkeypatch.setattr(record_usages.usage_settings, "disable_recording_node_usage", False)
    # Flush buffered PostgreSQL history on every cycle
    monkeypatch.setattr(record_usages.usage_settings, "user_usage_history_flush_interval", 0)

    for cycle in range(2):
        current["cycle"] = cycle
        await record_usages.record_user_usages()
        await record_usages.record_node_usages()

    expected_users = defaultdict(int)
    expected_admins = defaultdict(int)
    expected_history = defaultdict(int)
    for stats in cycles:
        for node_id, params in stats.items():
            for param in params:
                if param["uid"] not in user_admin:
                    continue
                value = int(param["value"] * coefficients[node_id])
                expected_users[param["uid"]] += value
                if user_admin[param["uid"]]:
                    expected_admins[user_admin[param["uid"]]] += value
                if value:
                    expected_history[(param["uid"], node_id)] += value
    expected_nodes = {
        node_id: (
            sum(outbound[node_id][0]["up"] for outbound in outbound_cycles),
            sum(outbound[node_id][0]["down"] for outbound in outbound_cycles),
        )
        for node_id in node_ids
    }

    async with session_factory() as session:
        user_rows = (await session.execute(select(User.id, User.used_traffic, User.online_at))).all()
        assert {row.id: row.used_traffic for row in user_rows} == {uid: expected_users[uid] for uid in user_ids}
        assert {row.id for row in user_rows if row.online_at is not None} == {
            uid for uid, value in expected_users.items() if value > 0
        }

        admin_rows = (await session.execute(select(Admin.id, Admin.used_traffic))).all()
        assert {row.id: row.used_traffic for row in admin_rows} == {
            admin_id: expected_admins[admin_id] for admin_id in admin_ids
        }

        history_rows = (
            await session.execute(
                select(
                    NodeUserUsage.created_at, NodeUserUsage.user_id, NodeUserUsage.node_id, NodeUserUsage.used_traffic
                )
            )
        ).all()
        assert len(history_rows) == len(expected_history)
        assert len({row.created_at for row in history_rows}) == 1
        assert {(row.user_id, row.node_id): row.used_traffic for row in history_rows} == dict(expected_history)

        node_rows = (await session.execute(select(Node.id, Node.uplink, Node.downlink))).all()
        assert {row.id: (row.uplink, row.downlink) for row in node_rows} == expected_nodes
        node_usage_rows = (await session.execute(select(NodeUsage.node_id, NodeUsage.uplink, NodeUsage.downlink))).all()
        assert {row.node_id: (row.uplink, row.downlink) for row in node_usage_rows} == expected_nodes
        system_row = (await session.execute(select(System.uplink, System.downlink))).one()
        assert tuple(system_row) == (
            sum(up for up, _ in expected_nodes.values()),
            sum(down for _, down in expected_nodes.values()),
        )


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
async def test_node_user_usage_history_skips_deleted_nodes(session_factory):
    async with session_factory() as session:
        user = User(username="user", proxy_settings=ProxyTable().dict(no_obj=True))
        deleted_node = Node(
            name="node-deleted",
            address="10.0.0.1",
            port=1000,
            api_port=1001,
            server_ca="ca1",
            api_key="key1",
            core_config_id=None,
        )
        kept_node = Node(
            name="node-kept",
            address="10.0.0.2",
            port=1002,
            api_port=1003,
            server_ca="ca2",
            api_key="key2",
            core_config_id=None,
        )
        session.add_all([user, deleted_node, kept_node])
        await session.flush()
        user_id, deleted_node_id, kept_node_id = user.id, deleted_node.id, kept_node.id
        await session.commit()

    # An admin deletes a node after its stats were read and before they are written
    async with session_factory() as session:
        await remove_node(session, await session.get(Node, deleted_node_id))

    bucket = record_usages._get_time_bucket()
    await record_usages._write_node_user_usage_params(
        await record_usages.get_dialect(),
        [
            {"uid": user_id, "value": 100, "node_id": deleted_node_id, "created_at": bucket},
            {"uid": user_id, "value": 50, "node_id": kept_node_id, "created_at": bucket},
        ],
    )

    async with session_factory() as session:
        rows = await session.execute(select(NodeUserUsage.node_id, NodeUserUsage.used_traffic))
        assert rows.all() == [(kept_node_id, 50)]


@pytest.mark.skipif(
    os.getenv("TEST_FROM", "local").lower() == "local" or not database_settings.url.startswith("postgresql"),
    reason="only PostgreSQL buffers node user usage history",
)
@pytest.mark.asyncio
async def test_postgres_history_keeps_flushing_after_a_node_is_deleted(
    monkeypatch: pytest.MonkeyPatch, session_factory
):
    async with session_factory() as session:
        user = User(username="user", proxy_settings=ProxyTable().dict(no_obj=True))
        node_a = Node(
            name="node-a",
            address="10.0.0.1",
            port=1000,
            api_port=1001,
            server_ca="ca1",
            api_key="key1",
            core_config_id=None,
        )
        node_b = Node(
            name="node-b",
            address="10.0.0.2",
            port=1002,
            api_port=1003,
            server_ca="ca2",
            api_key="key2",
            core_config_id=None,
        )
        session.add_all([user, node_a, node_b])
        await session.flush()
        user_id, node_a_id, node_b_id = user.id, node_a.id, node_b.id
        await session.commit()

    clock = {"t": 1000.0}
    monkeypatch.setattr(record_usages, "_monotonic_now", lambda: clock["t"])
    monkeypatch.setattr(record_usages.usage_settings, "user_usage_history_flush_interval", 60)
    coefficients = {node_a_id: 1.0, node_b_id: 1.0}

    # The first sample is written at once, the next one is buffered
    await record_usages.record_user_stats(
        {node_a_id: [{"uid": user_id, "value": 100}], node_b_id: [{"uid": user_id, "value": 100}]}, coefficients
    )
    clock["t"] += 5
    await record_usages.record_user_stats(
        {node_a_id: [{"uid": user_id, "value": 50}], node_b_id: [{"uid": user_id, "value": 50}]}, coefficients
    )

    # Node A is deleted while its sample is still buffered
    async with session_factory() as session:
        await remove_node(session, await session.get(Node, node_a_id))

    clock["t"] += 61
    await record_usages.flush_user_usage_history_if_due()
    for _ in range(5):
        clock["t"] += 61
        await record_usages.record_user_stats({node_b_id: [{"uid": user_id, "value": 10}]}, coefficients)

    async with session_factory() as session:
        totals = await session.execute(
            select(NodeUserUsage.node_id, func.sum(NodeUserUsage.used_traffic)).group_by(NodeUserUsage.node_id)
        )
        assert dict(totals.all()) == {node_b_id: 200}
    assert not record_usages._pending_user_usage_history


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

    # One executemany row list per 1000-row batch
    assert executed_param_sizes == [1_000, 1_000, 501]


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


@pytest.mark.asyncio
async def test_record_node_stats_batched_logs_write_errors(monkeypatch: pytest.MonkeyPatch, caplog):
    written_nodes = []

    async def fake_safe_execute(stmt, params=None, max_retries=5):
        if params[0]["node_id"] == 2:
            raise OperationalError("INSERT INTO node_usages", {}, Exception("database is locked"))
        written_nodes.append(params[0]["node_id"])

    monkeypatch.setattr(record_usages, "get_dialect", AsyncMock(return_value="postgresql"))
    monkeypatch.setattr(record_usages, "safe_execute", fake_safe_execute)
    caplog.set_level(logging.ERROR)

    await record_usages.record_node_stats_batched({1: [{"up": 10, "down": 4}], 2: [{"up": 1, "down": 1}]})

    assert written_nodes == [1]
    assert "Failed to record node usage history for node 2" in caplog.text
    assert "database is locked" in caplog.text


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
