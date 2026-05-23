import pytest
from fastapi import status
from sqlalchemy import select

from app.db.crud.hwid import register_user_hwid, reset_user_hwids
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


def test_hwid_respects_admin_role_policy(access_token):
    def _login(username: str, password: str) -> str:
        response = client.post(
            "/api/admin/token",
            data={"username": username, "password": password, "grant_type": "password"},
        )
        assert response.status_code == status.HTTP_200_OK
        return response.json()["access_token"]

    def _create_role(enabled: bool) -> dict:
        payload = {
            "name": unique_name(f"role_hwid_{'enabled' if enabled else 'disabled'}"),
            "permissions": {
                "users": {"create": True, "read": {"scope": 2}, "delete": {"scope": 2}},
            },
            "limits": {},
            "features": {},
            "access": {},
            "hwid": {"enabled": enabled, "forced": False},
        }
        response = client.post("/api/admin-role", headers=auth_headers(access_token), json=payload)
        assert response.status_code == status.HTTP_201_CREATED
        return response.json()

    role_off = _create_role(False)
    role_on = _create_role(True)
    admin_off = create_admin(access_token, role_id=role_off["id"])
    admin_on = create_admin(access_token, role_id=role_on["id"])
    user_off = None
    user_on = None

    try:
        off_token = _login(admin_off["username"], admin_off["password"])
        on_token = _login(admin_on["username"], admin_on["password"])

        user_off = create_user(off_token)
        user_on = create_user(on_token)

        off_sub_response = client.get(user_off["subscription_url"], headers={"X-HWID": "off-device"})
        assert off_sub_response.status_code == status.HTTP_200_OK

        on_sub_response = client.get(user_on["subscription_url"], headers={"X-HWID": "on-device"})
        assert on_sub_response.status_code == status.HTTP_200_OK

        off_hwids = client.get(f"/api/user/{user_off['id']}/hwids", headers=auth_headers(access_token)).json()
        on_hwids = client.get(f"/api/user/{user_on['id']}/hwids", headers=auth_headers(access_token)).json()

        assert off_hwids["count"] == 0
        assert on_hwids["count"] == 1
        assert on_hwids["hwids"][0]["hwid"] == "on-device"
    finally:
        if user_off is not None:
            delete_user(access_token, user_off["username"])
        if user_on is not None:
            delete_user(access_token, user_on["username"])
        delete_admin(access_token, admin_off["username"])
        delete_admin(access_token, admin_on["username"])
        client.delete(f"/api/admin-role/{role_off['id']}", headers=auth_headers(access_token))
        client.delete(f"/api/admin-role/{role_on['id']}", headers=auth_headers(access_token))
