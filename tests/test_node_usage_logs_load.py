"""Assert get_nodes / get_node_by_id respect load_usage_logs."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.crud.node import get_node_by_id, get_nodes
from app.db.models import Node, NodeUsageResetLogs
from app.models.node import NodeListQuery


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
        session.add(
            Node(
                name="n1",
                address="10.0.0.1",
                port=1000,
                api_port=1001,
                server_ca="ca",
                api_key="key",
                core_config_id=None,
            )
        )
        await session.commit()
        node = await get_node_by_id(session, 1, load_usage_logs=False)
        session.add(NodeUsageResetLogs(node_id=node.id, uplink=1, downlink=2))
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_nodes_skips_usage_logs_when_disabled(db_session):
    nodes, _ = await get_nodes(db_session, NodeListQuery(), load_usage_logs=False)
    assert len(nodes) == 1
    assert "usage_logs" in sa_inspect(nodes[0]).unloaded


@pytest.mark.asyncio
async def test_get_nodes_loads_usage_logs_by_default(db_session):
    nodes, _ = await get_nodes(db_session, NodeListQuery())
    assert len(nodes) == 1
    assert "usage_logs" not in sa_inspect(nodes[0]).unloaded
    assert len(nodes[0].usage_logs) == 1


@pytest.mark.asyncio
async def test_get_node_by_id_skips_usage_logs_when_disabled(db_session):
    node = await get_node_by_id(db_session, 1, load_usage_logs=False)
    assert node is not None
    assert "usage_logs" in sa_inspect(node).unloaded
