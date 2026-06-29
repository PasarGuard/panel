import asyncio
from unittest.mock import AsyncMock

from fastapi import status
from pytest import MonkeyPatch

from app.db.models import Admin, AdminRole, System
from app.models.admin import hash_password as _hash_password
from app.utils.system import CPUStat, DiskStat, MemoryStat
from tests.api import TestSession, client
from tests.api.helpers import auth_headers, unique_name


def test_system(access_token, monkeypatch: MonkeyPatch):
    system = System(873259981, 1547846375)
    system_mock = AsyncMock()
    system_mock.return_value = system
    monkeypatch.setattr("app.operation.system.get_system_usage", system_mock)
    monkeypatch.setattr("app.operation.system.memory_usage", lambda: MemoryStat(total=16_000, used=8_000, free=8_000))
    monkeypatch.setattr("app.operation.system.cpu_usage", lambda: CPUStat(cores=8, percent=42.5))
    monkeypatch.setattr("app.operation.system.disk_usage", lambda: DiskStat(total=100_000, used=40_000, free=60_000))
    monkeypatch.setattr("app.operation.system.get_uptime", lambda: 123)

    response = client.get(
        "/api/system",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["uptime_seconds"] == 123
    assert body["disk_total"] == 100_000
    assert body["disk_used"] == 40_000


def test_system_resource_stats_excludes_user_metrics(access_token, monkeypatch: MonkeyPatch):
    monkeypatch.setattr("app.operation.system.memory_usage", lambda: MemoryStat(total=16_000, used=8_000, free=8_000))
    monkeypatch.setattr("app.operation.system.cpu_usage", lambda: CPUStat(cores=8, percent=42.5))
    monkeypatch.setattr("app.operation.system.disk_usage", lambda: DiskStat(total=100_000, used=40_000, free=60_000))
    monkeypatch.setattr("app.operation.system.get_uptime", lambda: 123)

    response = client.get("/api/system/resources", headers=auth_headers(access_token))

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["uptime_seconds"] == 123
    assert body["disk_total"] == 100_000
    assert "total_user" not in body
    assert "online_users" not in body


def test_system_users_stats_requires_users_read_not_system_read():
    username = unique_name("system_users_admin")
    password = "SystemUsers#123"
    role_name = unique_name("system_users_role")

    async def _create_admin() -> tuple[int, int]:
        async with TestSession() as session:
            role = AdminRole(
                name=role_name,
                permissions={"users": {"read": True}},
                limits={},
                features={},
                access={},
                hwid={},
            )
            session.add(role)
            await session.flush()
            admin = Admin(username=username, hashed_password=await _hash_password(password), role_id=role.id)
            session.add(admin)
            await session.commit()
            return role.id, admin.id

    async def _cleanup(role_id: int, admin_id: int) -> None:
        async with TestSession() as session:
            admin = await session.get(Admin, admin_id)
            if admin:
                await session.delete(admin)
            role = await session.get(AdminRole, role_id)
            if role:
                await session.delete(role)
            await session.commit()

    role_id, admin_id = asyncio.run(_create_admin())
    try:
        token_response = client.post(
            "/api/admin/token",
            data={"username": username, "password": password, "grant_type": "password"},
        )
        assert token_response.status_code == status.HTTP_200_OK
        headers = auth_headers(token_response.json()["access_token"])

        users_response = client.get("/api/system/users", headers=headers)
        assert users_response.status_code == status.HTTP_200_OK
        assert "total_user" in users_response.json()
        assert "uptime_seconds" not in users_response.json()

        resources_response = client.get("/api/system/resources", headers=headers)
        assert resources_response.status_code == status.HTTP_403_FORBIDDEN

        legacy_response = client.get("/api/system", headers=headers)
        assert legacy_response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        asyncio.run(_cleanup(role_id, admin_id))
