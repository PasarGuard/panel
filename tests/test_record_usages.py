from __future__ import annotations

import os
from collections import defaultdict
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.db import base
from app.db.models import Admin, Node, NodeUsage, NodeUserUsage, System, User
from app.jobs import record_usages
from app.models.proxy import ProxyTable
from config import SQLALCHEMY_DATABASE_URL


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
    return SQLALCHEMY_DATABASE_URL


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

    yield session_factory

    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.drop_all)
    await engine.dispose()
    if needs_json_default_fix and proxy_column is not None:
        proxy_column.server_default = proxy_default


@pytest.mark.asyncio
async def test_record_user_usages_updates_users_and_admins(monkeypatch: pytest.MonkeyPatch, session_factory):
    async with session_factory() as session:
        admin = Admin(username="admin", hashed_password="secret")
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

    async def fake_get_users_stats(node: DummyNode):
        return stats_map[node.node_id]

    monkeypatch.setattr(record_usages, "get_users_stats", fake_get_users_stats)
    monkeypatch.setattr(record_usages, "DISABLE_RECORDING_NODE_USAGE", False)

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
async def test_record_user_usages_returns_when_no_usage(monkeypatch: pytest.MonkeyPatch, session_factory):
    async with session_factory() as session:
        admin = Admin(username="admin", hashed_password="secret")
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

    async def fake_get_users_stats(_: DummyNode):
        return []

    monkeypatch.setattr(record_usages, "get_users_stats", fake_get_users_stats)
    monkeypatch.setattr(record_usages, "DISABLE_RECORDING_NODE_USAGE", False)

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

    async def fake_get_outbounds_stats(node: DummyNode):
        return stats_map[node.node_id]

    monkeypatch.setattr(record_usages, "get_outbounds_stats", fake_get_outbounds_stats)
    monkeypatch.setattr(record_usages, "DISABLE_RECORDING_NODE_USAGE", False)

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

    async def fake_get_outbounds_stats(_: DummyNode):
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
