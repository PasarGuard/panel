from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import base
from app.db.crud import node as node_crud
from app.db.models import DataLimitResetStrategy, Node, NodeStatus, NodeUsageResetLogs
from app.models.node import NodeResponse

NOW = datetime(2026, 9, 17, 12, tzinfo=UTC)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(base.Base.metadata.create_all)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


async def add_node(db, name, strategy, reset_time, last_reset, with_history, status=NodeStatus.connected):
    node = Node(
        name=name,
        address="127.0.0.1",
        port=1000,
        api_port=1001,
        server_ca="ca",
        api_key="key",
        core_config_id=None,
        status=status,
        data_limit_reset_strategy=strategy,
        reset_time=reset_time,
        uplink=123,
        downlink=456,
    )
    node.created_at = last_reset - timedelta(days=800) if with_history else last_reset
    db.add(node)
    await db.flush()
    if with_history:
        # Insert the newest timestamp first so row/insertion order cannot determine it.
        for timestamp in (last_reset, last_reset - timedelta(days=400)):
            log = NodeUsageResetLogs(node_id=node.id, uplink=10, downlink=20)
            log.created_at = timestamp
            db.add(log)
    await db.commit()
    return node.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy", "reset_time", "old_reset"),
    [
        (DataLimitResetStrategy.day, 3600, NOW - timedelta(days=1)),
        (DataLimitResetStrategy.week, 3600, NOW - timedelta(days=8)),
        (DataLimitResetStrategy.month, 86400 + 3600, NOW - timedelta(days=40)),
        (DataLimitResetStrategy.year, 86400 + 3600, NOW - timedelta(days=400)),
    ],
)
@pytest.mark.parametrize("with_history", [False, True])
@pytest.mark.parametrize("due", [False, True])
async def test_scheduled_reset_candidates(db_session, monkeypatch, strategy, reset_time, old_reset, with_history, due):
    monkeypatch.setattr(node_crud, "datetime", FrozenDatetime)
    node_id = await add_node(db_session, "scheduled", strategy, reset_time, old_reset if due else NOW, with_history)
    db_session.expunge_all()
    statements = []

    def record_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        nodes = await node_crud.get_nodes_to_reset_usage(db_session)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert [node.id for node in nodes] == ([node_id] if due else [])
    assert len(statements) == 1
    assert all("usage_logs" in inspect(node).unloaded for node in nodes)
    assert not any(isinstance(obj, NodeUsageResetLogs) for obj in db_session.identity_map.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("with_history", [False, True])
async def test_interval_candidates_and_bulk_reset_remain_compatible(db_session, with_history):
    now = datetime.now(UTC)
    expected_ids = []
    for status in NodeStatus:
        node_id = await add_node(
            db_session, status.value, DataLimitResetStrategy.day, -1, now - timedelta(days=2), with_history, status
        )
        if status != NodeStatus.disabled:
            expected_ids.append(node_id)
    await add_node(db_session, "recent", DataLimitResetStrategy.day, -1, now, with_history)
    await add_node(db_session, "no-reset", DataLimitResetStrategy.no_reset, -1, now - timedelta(days=800), with_history)
    db_session.expunge_all()

    nodes = await node_crud.get_nodes_to_reset_usage(db_session)
    assert {node.id for node in nodes} == set(expected_ids)
    assert all("usage_logs" in inspect(node).unloaded for node in nodes)

    updated_nodes = await node_crud.bulk_reset_node_usage(db_session, nodes)
    assert [node.id for node in updated_nodes] == [node.id for node in nodes]
    for node in updated_nodes:
        response = NodeResponse.model_validate(node)
        assert response.uplink == response.downlink == 0
        assert node.status != NodeStatus.limited
        latest_log = max(node.usage_logs, key=lambda log: log.created_at)
        assert (latest_log.uplink, latest_log.downlink) == (123, 456)
        assert len(node.usage_logs) == (3 if with_history else 1)
