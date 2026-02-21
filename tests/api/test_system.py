from unittest.mock import AsyncMock

from fastapi import status
from pytest import MonkeyPatch

from app.db.models import System
from app.utils.system import CPUStat, DiskStat, MemoryStat
from tests.api import client


def test_system(access_token, monkeypatch: MonkeyPatch):
    system = System(873259981, 1547846375)
    system_mock = AsyncMock()
    system_mock.return_value = system
    monkeypatch.setattr("app.operation.system.get_system_usage", system_mock)
    monkeypatch.setattr("app.operation.system.memory_usage", lambda: MemoryStat(total=16_000, used=8_000, free=8_000))
    monkeypatch.setattr("app.operation.system.cpu_usage", lambda: CPUStat(cores=8, percent=42.5))
    monkeypatch.setattr("app.operation.system.disk_usage", lambda: DiskStat(total=100_000, used=40_000, free=60_000))

    response = client.get(
        "/api/system",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["disk_total"] == 100_000
    assert body["disk_used"] == 40_000
