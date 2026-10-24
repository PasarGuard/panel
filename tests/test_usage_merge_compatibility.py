from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import mysql

from app.jobs import record_usages
from app.jobs._usage_storage import UsageStore


async def test_mysql_receipt_accounting_uses_set_based_traffic_update():
    conn = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(1, None), (2, None)])))
    now = datetime.now(UTC)
    payload = {
        "stats": [{"uid": 1, "value": 10}, {"uid": 1, "value": 5}, {"uid": 2, "value": 20}],
        "coefficient": 2,
        "history": False,
    }

    await UsageStore(None, "mysql")._users(conn, 1, payload, now, now)

    traffic_update = conn.execute.await_args_list[1]
    compiled = traffic_update.args[0].compile(dialect=mysql.dialect())
    assert "CASE users.id" in str(compiled)
    assert 30 in compiled.params.values()
    assert 40 in compiled.params.values()
    assert traffic_update.args[1] is None


@pytest.mark.parametrize("coefficient, expected", [(None, 1.0), (0, 0.0), (2, 2.0)])
async def test_usage_coefficient_preserves_optional_and_zero_values(monkeypatch, coefficient, expected):
    monkeypatch.setattr(record_usages, "_usage_coefficient_cache", {})
    node = SimpleNamespace(get_extra=AsyncMock(return_value={"usage_coefficient": coefficient}))
    assert await record_usages._node_usage_coefficient(node, 1) == expected


@pytest.mark.parametrize("coefficient", [-1, float("nan"), float("inf")])
async def test_usage_coefficient_rejects_invalid_values_before_collection(monkeypatch, coefficient):
    monkeypatch.setattr(record_usages, "_usage_coefficient_cache", {})
    node = SimpleNamespace(get_extra=AsyncMock(return_value={"usage_coefficient": coefficient}))
    with pytest.raises(ValueError, match="Invalid usage coefficient"):
        await record_usages._node_usage_coefficient(node, 1)
