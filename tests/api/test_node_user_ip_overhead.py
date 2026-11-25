from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from app.db.models import Admin, User
from app.operation import OperatorType
from app.operation.node import NodeOperation
from tests.api import TestSession, engine
from tests.api.helpers import unique_name

pytestmark = pytest.mark.asyncio

OVERHEAD_TABLES = ("admins", "next_plans", "user_usage_logs", "groups")


async def _seed_user_with_relations() -> int:
    async with TestSession() as session:
        admin = Admin(username=unique_name("ovh_admin"), hashed_password="secret", role_id=3)
        session.add(admin)
        await session.flush()
        user = User(username=unique_name("ovh_user"), admin_id=admin.id)
        session.add(user)
        await session.commit()
        return user.id


def _count_overhead_queries():
    counts = {table: 0 for table in OVERHEAD_TABLES}

    def count_queries(conn, cursor, statement, parameters, context, executemany):
        lowered = statement.lower()
        for table in OVERHEAD_TABLES:
            if table in lowered:
                counts[table] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_queries)
    return counts, count_queries


@pytest.mark.parametrize(
    "method_name",
    ["_get_user_online_stats_local", "_get_user_ip_list_local", "_get_user_ip_list_all_local"],
)
async def test_local_user_ip_methods_skip_unneeded_relations(method_name, monkeypatch):
    user_id = await _seed_user_with_relations()
    operator = NodeOperation(operator_type=OperatorType.API)
    fake_stats = SimpleNamespace(value={1: 2})
    fake_ips = SimpleNamespace(ips={"1.2.3.4": 2})
    fake_node = SimpleNamespace(
        get_user_online_stats=AsyncMock(return_value=fake_stats),
        get_user_online_ip_list=AsyncMock(return_value=fake_ips),
    )
    monkeypatch.setattr(
        "app.operation.node.node_manager",
        SimpleNamespace(get_node=AsyncMock(return_value=fake_node), get_healthy_nodes=AsyncMock(return_value=[])),
    )

    counts, listener = _count_overhead_queries()
    try:
        async with TestSession() as session:
            if method_name == "_get_user_ip_list_all_local":
                method = getattr(operator, method_name)
                result = await method(db=session, user_id=user_id)
                assert result is not None
            else:
                method = getattr(operator, method_name)
                result = await method(db=session, node_id=1, user_id=user_id)
                assert result is not None
        for table, count in counts.items():
            assert count == 0, f"unexpected queries against {table}"
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)


@pytest.mark.parametrize(
    "method_name",
    ["_get_user_online_stats_local", "_get_user_ip_list_local", "_get_user_ip_list_all_local"],
)
async def test_local_user_ip_methods_missing_user_still_404(method_name, monkeypatch):
    operator = NodeOperation(operator_type=OperatorType.API)
    fake_node = SimpleNamespace(
        get_user_online_stats=AsyncMock(return_value=SimpleNamespace(value={})),
        get_user_online_ip_list=AsyncMock(return_value=SimpleNamespace(ips={})),
    )
    monkeypatch.setattr(
        "app.operation.node.node_manager",
        SimpleNamespace(get_node=AsyncMock(return_value=fake_node), get_healthy_nodes=AsyncMock(return_value=[])),
    )

    async with TestSession() as session:
        method = getattr(operator, method_name)
        with pytest.raises(HTTPException) as exc_info:
            if method_name == "_get_user_ip_list_all_local":
                await method(db=session, user_id=999999)
            else:
                await method(db=session, node_id=1, user_id=999999)
        assert exc_info.value.status_code == 404
