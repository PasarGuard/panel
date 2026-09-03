"""Regression tests for scalable node-list lifetime usage loading."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.crud.node import get_nodes
from app.db.models import Node, NodeUsageResetLogs
from app.models.node import NodeListQuery
from app.operation import OperatorType
from app.operation.node import NodeOperation


@pytest_asyncio.fixture
async def seeded_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with factory() as session:
            nodes = [
                Node(
                    name="aggregate-node-with-history",
                    address="10.0.0.1",
                    port=62050,
                    api_port=62051,
                    server_ca="ca",
                    api_key="key-1",
                    core_config_id=None,
                    uplink=7,
                    downlink=11,
                ),
                Node(
                    name="aggregate-node-without-history",
                    address="10.0.0.2",
                    port=62050,
                    api_port=62051,
                    server_ca="ca",
                    api_key="key-2",
                    core_config_id=None,
                    uplink=13,
                    downlink=17,
                ),
            ]
            session.add_all(nodes)
            await session.flush()
            session.add_all(
                [
                    NodeUsageResetLogs(node_id=nodes[0].id, uplink=19, downlink=23),
                    NodeUsageResetLogs(node_id=nodes[0].id, uplink=29, downlink=31),
                ]
            )
            await session.commit()

        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_nodes_aggregates_lifetime_usage_without_loading_history(seeded_session):
    nodes, total = await get_nodes(
        seeded_session,
        NodeListQuery(limit=10),
        load_usage_logs=False,
        load_lifetime_usage=True,
    )

    assert total == 2
    assert [(node.lifetime_uplink, node.lifetime_downlink) for node in nodes] == [(55, 65), (13, 17)]
    assert all("usage_logs" in sa_inspect(node).unloaded for node in nodes)


@pytest.mark.asyncio
async def test_panel_node_list_requests_aggregates_instead_of_history(monkeypatch):
    load_nodes = AsyncMock(return_value=([], 0))
    monkeypatch.setattr("app.operation.node.get_nodes", load_nodes)
    operator = NodeOperation(OperatorType.WEB)

    response = await operator.get_db_nodes(object(), NodeListQuery())

    assert response.total == 0
    assert load_nodes.await_args.kwargs["load_usage_logs"] is False
    assert load_nodes.await_args.kwargs["load_lifetime_usage"] is True
