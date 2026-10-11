import asyncio

import pytest
from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.crud.hwid import get_user_hwid_count, register_user_hwid, reset_user_hwids
from app.db.models import User as DBUser, UserHWID
from app.models.settings import HWIDSettings
from tests.api import DATABASE_URL, IS_SQLITE, TestSession, client
from tests.api.helpers import (
    auth_headers,
    create_admin,
    create_user,
    delete_admin,
    delete_user,
    unique_name,
)


async def _set_user_hwid_limit(user_id: int, hwid_limit: int | None) -> None:
    async with TestSession() as session:
        await reset_user_hwids(session, user_id)
        db_user = (await session.execute(select(DBUser).where(DBUser.id == user_id))).scalar_one()
        db_user.hwid_limit = hwid_limit
        await session.commit()


async def _reset_user_hwids(user_id: int) -> None:
    async with TestSession() as session:
        await reset_user_hwids(session, user_id)


@pytest.mark.asyncio
async def test_register_user_hwid_upserts_existing_row(access_token):
    user = create_user(access_token)

    try:
        async with TestSession() as session:
            await register_user_hwid(session, user["id"], "device-dup", "Android", "14", "Pixel 8")
            inserted = (
                await session.execute(
                    select(UserHWID).where(UserHWID.user_id == user["id"], UserHWID.hwid == "device-dup")
                )
            ).scalar_one()
            first_last_used_at = inserted.last_used_at

        async with TestSession() as session:
            await register_user_hwid(session, user["id"], "device-dup")
            updated = (
                await session.execute(
                    select(UserHWID).where(UserHWID.user_id == user["id"], UserHWID.hwid == "device-dup")
                )
            ).scalar_one()
            rows = (
                (
                    await session.execute(
                        select(UserHWID).where(UserHWID.user_id == user["id"], UserHWID.hwid == "device-dup")
                    )
                )
                .scalars()
                .all()
            )

        assert len(rows) == 1
        assert updated.id == inserted.id
        assert updated.device_os == "Android"
        assert updated.os_version == "14"
        assert updated.device_model == "Pixel 8"
        assert updated.last_used_at >= first_last_used_at
    finally:
        async with TestSession() as session:
            await reset_user_hwids(session, user["id"])
        delete_user(access_token, user["username"])


def test_hwid_workflow(access_token):
    """
    Test the full HWID workflow:
    1. Create a user
    2. Fetch subscription with HWID headers (Registration)
    3. Verify HWID is registered via Admin API
    4. Fetch subscription with different HWID (Limit check)
    5. Delete HWID via Admin API
    6. Reset all HWIDs for user
    """
    # 1. Create a user
    user = create_user(access_token)
    user_id = user["id"]
    sub_url = user["subscription_url"]
    assert user["hwid_limit"] is None

    try:
        # 2. Fetch subscription with HWID headers (Registration)
        hwid1 = "device-ios-123"
        headers1 = {"X-HWID": hwid1, "X-Device-OS": "iOS", "X-Ver-OS": "16.5", "X-Device-Model": "iPhone 14"}
        response = client.get(sub_url, headers=headers1)
        assert response.status_code == status.HTTP_200_OK

        # 3. Verify HWID is registered via Admin API
        response = client.get(f"/api/user/{user_id}/hwids", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == 1
        item = data["hwids"][0]
        assert item["hwid"] == hwid1
        assert item["device_os"] == "iOS"
        assert item["os_version"] == "16.5"
        assert item["device_model"] == "iPhone 14"

        # 4. Fetch subscription with different HWID (Up to limit)
        # fallback_limit is 3 in conftest.py
        response = client.get(sub_url, headers={"X-HWID": "device-2"})
        assert response.status_code == status.HTTP_200_OK
        response = client.get(sub_url, headers={"X-HWID": "device-3"})
        assert response.status_code == status.HTTP_200_OK

        response = client.get(f"/api/user/{user_id}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 3

        # 4b. 4th device should fail
        response = client.get(sub_url, headers={"X-HWID": "device-4"})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Device limit reached" in response.json()["detail"]

        # 5. Delete one HWID via Admin API
        response = client.delete(f"/api/user/{user_id}/hwids/{hwid1}", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_200_OK

        response = client.get(f"/api/user/{user_id}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 2

        # 6. Reset all HWIDs for user
        response = client.post(f"/api/user/{user_id}/hwids/reset", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_200_OK

        response = client.get(f"/api/user/{user_id}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 0

    finally:
        delete_user(access_token, user["username"])


@pytest.mark.asyncio
async def test_hwid_enabled_applies_to_users_with_explicit_limit(access_token):
    user = create_user(access_token)

    try:
        await _set_user_hwid_limit(user["id"], 1)

        response = client.get(user["subscription_url"], headers={"X-HWID": "explicit-device-1"})
        assert response.status_code == status.HTTP_200_OK

        response = client.get(user["subscription_url"], headers={"X-HWID": "explicit-device-2"})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Device limit reached" in response.json()["detail"]

        response = client.get(f"/api/user/{user['id']}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 1
        assert response.json()["hwids"][0]["hwid"] == "explicit-device-1"
    finally:
        await _reset_user_hwids(user["id"])
        delete_user(access_token, user["username"])


@pytest.mark.asyncio
async def test_hwid_enabled_applies_fallback_to_user_without_limit(access_token):
    user = create_user(access_token)

    try:
        await _set_user_hwid_limit(user["id"], None)

        for index in range(3):
            response = client.get(user["subscription_url"], headers={"X-HWID": f"null-limit-device-{index}"})
            assert response.status_code == status.HTTP_200_OK

        response = client.get(user["subscription_url"], headers={"X-HWID": "null-limit-device-4"})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Device limit reached" in response.json()["detail"]

        response = client.get(f"/api/user/{user['id']}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 3
    finally:
        await _reset_user_hwids(user["id"])
        delete_user(access_token, user["username"])


@pytest.mark.asyncio
async def test_hwid_forced_applies_fallback_to_user_without_limit(access_token, monkeypatch):
    from app.models.settings import HWIDSettings
    from app.operation import subscription as subscription_module

    user = create_user(access_token)

    try:
        await _set_user_hwid_limit(user["id"], None)

        async def forced_hwid_settings() -> HWIDSettings:
            return HWIDSettings(enabled=True, forced=True, fallback_limit=3, min_limit=1, max_limit=0)

        monkeypatch.setattr(subscription_module, "hwid_settings", forced_hwid_settings)

        response = client.get(user["subscription_url"])
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "HWID header required" in response.json()["detail"]

        for index in range(3):
            response = client.get(user["subscription_url"], headers={"X-HWID": f"forced-fallback-device-{index}"})
            assert response.status_code == status.HTTP_200_OK

        response = client.get(user["subscription_url"], headers={"X-HWID": "forced-fallback-device-4"})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Device limit reached" in response.json()["detail"]

        response = client.get(f"/api/user/{user['id']}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 3
    finally:
        await _reset_user_hwids(user["id"])
        delete_user(access_token, user["username"])


def test_hwid_respects_admin_role_policy(access_token):
    def _login(username: str, password: str) -> str:
        response = client.post(
            "/api/admin/token",
            data={"username": username, "password": password, "grant_type": "password"},
        )
        assert response.status_code == status.HTTP_200_OK
        return response.json()["access_token"]

    def _create_role(mode: str) -> dict:
        payload = {
            "name": unique_name(f"role_hwid_{mode}"),
            "permissions": {
                "users": {"create": True, "read": {"scope": 2}, "delete": {"scope": 2}},
            },
            "limits": {},
            "features": {},
            "access": {},
            "hwid": {"mode": mode, "forced": False},
        }
        response = client.post("/api/admin-role", headers=auth_headers(access_token), json=payload)
        assert response.status_code == status.HTTP_201_CREATED
        return response.json()

    role_disabled = _create_role("disabled")
    role_use_global = _create_role("use_global")
    admin_disabled = create_admin(access_token, role_id=role_disabled["id"])
    admin_use_global = create_admin(access_token, role_id=role_use_global["id"])
    user_disabled = None
    user_use_global = None

    try:
        disabled_token = _login(admin_disabled["username"], admin_disabled["password"])
        use_global_token = _login(admin_use_global["username"], admin_use_global["password"])

        user_disabled = create_user(disabled_token)
        user_use_global = create_user(use_global_token)

        disabled_sub_response = client.get(user_disabled["subscription_url"], headers={"X-HWID": "disabled-device"})
        assert disabled_sub_response.status_code == status.HTTP_200_OK

        use_global_sub_response = client.get(user_use_global["subscription_url"], headers={"X-HWID": "global-device"})
        assert use_global_sub_response.status_code == status.HTTP_200_OK

        disabled_hwids = client.get(f"/api/user/{user_disabled['id']}/hwids", headers=auth_headers(access_token)).json()
        use_global_hwids = client.get(
            f"/api/user/{user_use_global['id']}/hwids", headers=auth_headers(access_token)
        ).json()

        assert disabled_hwids["count"] == 0
        assert use_global_hwids["count"] == 1
        assert use_global_hwids["hwids"][0]["hwid"] == "global-device"
    finally:
        if user_disabled is not None:
            delete_user(access_token, user_disabled["username"])
        if user_use_global is not None:
            delete_user(access_token, user_use_global["username"])
        delete_admin(access_token, admin_disabled["username"])
        delete_admin(access_token, admin_use_global["username"])
        client.delete(f"/api/admin-role/{role_disabled['id']}", headers=auth_headers(access_token))
        client.delete(f"/api/admin-role/{role_use_global['id']}", headers=auth_headers(access_token))


def test_hwid_override_mode_with_custom_limits(access_token):
    """Test that override mode allows custom limits to take effect."""

    def _login(username: str, password: str) -> str:
        response = client.post(
            "/api/admin/token",
            data={"username": username, "password": password, "grant_type": "password"},
        )
        assert response.status_code == status.HTTP_200_OK
        return response.json()["access_token"]

    # Create role with override mode and custom fallback_limit=2 (global is 3)
    payload = {
        "name": unique_name("role_hwid_override"),
        "permissions": {
            "users": {"create": True, "read": {"scope": 2}, "delete": {"scope": 2}},
        },
        "limits": {},
        "features": {},
        "access": {},
        "hwid": {"mode": "override", "forced": False, "fallback_limit": 2},
    }
    response = client.post("/api/admin-role", headers=auth_headers(access_token), json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    role = response.json()
    admin = create_admin(access_token, role_id=role["id"])
    user = None

    try:
        token = _login(admin["username"], admin["password"])
        user = create_user(token)

        # Register 2 devices (the override fallback_limit)
        client.get(user["subscription_url"], headers={"X-HWID": "ov-device-1"})
        client.get(user["subscription_url"], headers={"X-HWID": "ov-device-2"})

        # 3rd device should fail (override limit is 2, not global 3)
        response = client.get(user["subscription_url"], headers={"X-HWID": "ov-device-3"})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Device limit reached" in response.json()["detail"]
    finally:
        if user is not None:
            delete_user(access_token, user["username"])
        delete_admin(access_token, admin["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))


@pytest.mark.asyncio
async def test_blank_hwid_header_counts_as_absent(access_token):
    user = create_user(access_token)

    try:
        await _reset_user_hwids(user["id"])
        for blank in ("", "   "):
            response = client.get(user["subscription_url"], headers={"X-HWID": blank})
            assert response.status_code == status.HTTP_200_OK

        response = client.get(user["subscription_url"], headers={"X-HWID": "x" * 257})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = client.get(f"/api/user/{user['id']}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 0
    finally:
        await _reset_user_hwids(user["id"])
        delete_user(access_token, user["username"])


@pytest.mark.asyncio
async def test_hwid_with_control_characters_is_rejected(access_token):
    user = create_user(access_token)

    try:
        await _reset_user_hwids(user["id"])
        # Raw header bytes: Starlette decodes them as latin-1, so 0x85 and 0x9f arrive as C1 controls.
        for hwid in (b"device\x01one", b"device\x7fone", b"device\x85one", b"device\x9fone"):
            response = client.get(user["subscription_url"], headers={"X-HWID": hwid})
            assert response.status_code == status.HTTP_400_BAD_REQUEST, hwid

        response = client.get(f"/api/user/{user['id']}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 0
    finally:
        await _reset_user_hwids(user["id"])
        delete_user(access_token, user["username"])


@pytest.mark.asyncio
async def test_long_device_info_headers_are_clipped(access_token):
    user = create_user(access_token)
    headers = {
        "X-HWID": "long-info-device",
        "X-Device-OS": "o" * 300,
        "X-Ver-OS": "v" * 300,
        "X-Device-Model": "m" * 300,
    }

    try:
        await _reset_user_hwids(user["id"])
        response = client.get(user["subscription_url"], headers=headers)
        assert response.status_code == status.HTTP_200_OK

        response = client.get(f"/api/user/{user['id']}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 1
        item = response.json()["hwids"][0]
        assert item["device_os"] == "o" * 256
        assert item["os_version"] == "v" * 128
        assert item["device_model"] == "m" * 256
    finally:
        await _reset_user_hwids(user["id"])
        delete_user(access_token, user["username"])


@pytest.mark.asyncio
async def test_concurrent_registrations_respect_device_limit(access_token):
    if ":memory:" in DATABASE_URL:
        pytest.skip("needs a database that separate connections share")

    user = create_user(access_token)
    # Independent connections, so the parent-row lock is really contended.
    racing_engine = create_async_engine(
        DATABASE_URL, poolclass=NullPool, connect_args={"timeout": 30} if IS_SQLITE else {}
    )
    racing_session = async_sessionmaker(racing_engine, expire_on_commit=False)

    async def register(hwid: str) -> bool:
        async with racing_session() as session:
            return await register_user_hwid(session, user["id"], hwid, limit=1)

    try:
        await _set_user_hwid_limit(user["id"], 1)

        results = await asyncio.gather(*(register(f"race-device-{index}") for index in range(4)))

        assert sorted(results) == [False, False, False, True]
        async with TestSession() as session:
            assert await get_user_hwid_count(session, user["id"]) == 1
    finally:
        await racing_engine.dispose()
        await _reset_user_hwids(user["id"])
        delete_user(access_token, user["username"])


def test_subscription_info_and_raw_omit_proxy_credentials(access_token):
    user = create_user(access_token)

    try:
        response = client.get(f"{user['subscription_url']}/info")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["username"] == user["username"]
        assert "proxy_settings" not in response.json()

        response = client.get(f"{user['subscription_url']}/raw")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["body"]["user"]["username"] == user["username"]
        assert "proxy_settings" not in response.json()["body"]["user"]
    finally:
        delete_user(access_token, user["username"])


@pytest.mark.parametrize("require_hwid_for_manual_sub", [False, True])
def test_raw_subscription_respects_manual_sub_hwid_gate(access_token, monkeypatch, require_hwid_for_manual_sub):
    from app.operation import subscription as subscription_module

    async def gated_hwid_settings() -> HWIDSettings:
        return HWIDSettings(
            enabled=True,
            require_hwid_for_manual_sub=require_hwid_for_manual_sub,
            fallback_limit=3,
            min_limit=1,
            max_limit=0,
        )

    async def fake_fetch_config(self, user, client_type):
        return "vless://gate-check", "text/plain"

    monkeypatch.setattr(subscription_module, "hwid_settings", gated_hwid_settings)
    monkeypatch.setattr(subscription_module.SubscriptionOperation, "fetch_config", fake_fetch_config)
    user = create_user(access_token)

    try:
        response = client.get(f"{user['subscription_url']}/raw")
        assert response.status_code == status.HTTP_200_OK
        expected = [] if require_hwid_for_manual_sub else ["vless://gate-check"]
        assert response.json()["body"]["links"] == expected
    finally:
        delete_user(access_token, user["username"])
