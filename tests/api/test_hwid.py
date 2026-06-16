import pytest
from fastapi import status
from sqlalchemy import select

from app.db.crud.hwid import register_user_hwid, reset_user_hwids
from app.db.models import User as DBUser
from app.db.models import UserHWID
from tests.api import TestSession, client
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
async def test_hwid_enabled_does_not_apply_fallback_to_user_without_limit(access_token):
    user = create_user(access_token)

    try:
        await _set_user_hwid_limit(user["id"], None)

        for index in range(4):
            response = client.get(user["subscription_url"], headers={"X-HWID": f"null-limit-device-{index}"})
            assert response.status_code == status.HTTP_200_OK

        response = client.get(f"/api/user/{user['id']}/hwids", headers=auth_headers(access_token))
        assert response.json()["count"] == 0
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


@pytest.mark.asyncio
async def test_subscription_apps_are_filtered_by_hwid_policy(access_token, monkeypatch):
    from app.operation import subscription as subscription_module

    applications = [
        {
            "name": "StandardApp",
            "icon_url": "",
            "import_url": "standard://import/{url}",
            "description": {"en": "Standard subscription app"},
            "recommended": True,
            "show_when_hwid_enabled": False,
            "platform": "android",
            "download_links": [{"name": "Download", "url": "https://example.com/standard", "language": "en"}],
        },
        {
            "name": "DeviceBoundApp",
            "icon_url": "",
            "import_url": "device://import/{url}",
            "description": {"en": "Device-bound subscription app"},
            "recommended": True,
            "show_when_hwid_enabled": True,
            "platform": "android",
            "download_links": [{"name": "Download", "url": "https://example.com/device-bound", "language": "en"}],
        },
    ]
    sub_settings = await subscription_module.subscription_settings()
    sub_settings_data = sub_settings.model_dump(mode="json")
    sub_settings_data["applications"] = applications
    patched_sub_settings = subscription_module.SubSettings.model_validate(sub_settings_data)

    async def patched_subscription_settings() -> subscription_module.SubSettings:
        return patched_sub_settings

    monkeypatch.setattr(subscription_module, "subscription_settings", patched_subscription_settings)
    user = create_user(access_token)

    try:
        await _set_user_hwid_limit(user["id"], None)
        response = client.get(f"{user['subscription_url']}/apps")
        assert response.status_code == status.HTTP_200_OK
        assert [app["name"] for app in response.json()] == ["StandardApp"]

        await _set_user_hwid_limit(user["id"], 1)
        response = client.get(f"{user['subscription_url']}/apps")
        assert response.status_code == status.HTTP_200_OK
        assert [app["name"] for app in response.json()] == ["DeviceBoundApp"]
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
