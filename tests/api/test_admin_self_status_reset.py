import asyncio

from fastapi import status
from sqlalchemy import select

from app.db.models import Admin, AdminStatus
from tests.api import TestSession, client
from tests.api.helpers import auth_headers, create_admin, delete_admin, unique_name


def _reseller(access_token: str) -> tuple[dict, dict, dict[str, str]]:
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("role_self_status"),
            "permissions": {"admins": {"read": True, "update": True, "reset_usage": True}},
            "limits": {},
            "features": {},
            "access": {},
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    role = response.json()
    admin = create_admin(access_token, role_id=role["id"])
    token = client.post(
        "/api/admin/token",
        data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
    ).json()["access_token"]
    return role, admin, auth_headers(token)


def _set_stored(username: str, **values) -> None:
    async def _update() -> None:
        async with TestSession() as session:
            row = (await session.execute(select(Admin).where(Admin.username == username))).scalar_one()
            for key, value in values.items():
                setattr(row, key, value)
            await session.commit()

    asyncio.run(_update())


def _stored(username: str) -> Admin:
    async def _load() -> Admin:
        async with TestSession() as session:
            return (await session.execute(select(Admin).where(Admin.username == username))).scalar_one()

    return asyncio.run(_load())


def _cleanup(access_token: str, role: dict, admin: dict) -> None:
    delete_admin(access_token, admin["username"])
    client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))


def test_a_limited_admin_cannot_set_its_own_status_back_to_active(access_token):
    role, admin, headers = _reseller(access_token)
    try:
        _set_stored(admin["username"], status=AdminStatus.limited)
        response = client.put(f"/api/admin/{admin['id']}", headers=headers, json={"status": "active"})
        assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
        assert _stored(admin["username"]).status == AdminStatus.limited
    finally:
        _cleanup(access_token, role, admin)


def test_a_non_owner_admin_cannot_reset_its_own_usage(access_token):
    role, admin, headers = _reseller(access_token)
    try:
        _set_stored(admin["username"], used_traffic=1024**3)
        response = client.post(f"/api/admin/{admin['id']}/reset", headers=headers)
        assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
        assert _stored(admin["username"]).used_traffic == 1024**3
    finally:
        _cleanup(access_token, role, admin)


def test_an_owner_session_can_still_reset_and_reactivate_another_admin(access_token):
    role, admin, _ = _reseller(access_token)
    try:
        _set_stored(admin["username"], status=AdminStatus.limited, used_traffic=1024**3)
        reset = client.post(f"/api/admin/{admin['id']}/reset", headers=auth_headers(access_token))
        assert reset.status_code == status.HTTP_200_OK, reset.text
        assert _stored(admin["username"]).used_traffic == 0
    finally:
        _cleanup(access_token, role, admin)


def test_a_non_owner_admin_cannot_bulk_reset_its_own_usage(access_token):
    role, admin, headers = _reseller(access_token)
    other = create_admin(access_token)
    try:
        _set_stored(admin["username"], used_traffic=1024**3)
        _set_stored(other["username"], used_traffic=1024**3)
        response = client.post("/api/admins/bulk/reset", headers=headers, json={"ids": [other["id"], admin["id"]]})
        assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
        assert _stored(admin["username"]).used_traffic == 1024**3
        assert _stored(other["username"]).used_traffic == 1024**3
    finally:
        delete_admin(access_token, other["username"])
        _cleanup(access_token, role, admin)


def test_a_non_owner_admin_can_still_bulk_reset_other_admins(access_token):
    role, admin, headers = _reseller(access_token)
    other = create_admin(access_token)
    try:
        _set_stored(admin["username"], used_traffic=1024**3)
        _set_stored(other["username"], used_traffic=1024**3)
        response = client.post("/api/admins/bulk/reset", headers=headers, json={"ids": [other["id"]]})
        assert response.status_code == status.HTTP_200_OK, response.text
        assert _stored(other["username"]).used_traffic == 0
        assert _stored(admin["username"]).used_traffic == 1024**3
    finally:
        delete_admin(access_token, other["username"])
        _cleanup(access_token, role, admin)


def test_an_owner_can_bulk_reset_itself_and_other_admins(access_token):
    role, admin, _ = _reseller(access_token)
    owner = create_admin(access_token)
    _set_stored(owner["username"], role_id=1)
    owner_token = client.post(
        "/api/admin/token",
        data={"username": owner["username"], "password": owner["password"], "grant_type": "password"},
    ).json()["access_token"]
    try:
        _set_stored(owner["username"], used_traffic=1024**3)
        _set_stored(admin["username"], used_traffic=1024**3)
        response = client.post(
            "/api/admins/bulk/reset", headers=auth_headers(owner_token), json={"ids": [owner["id"], admin["id"]]}
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert _stored(owner["username"]).used_traffic == 0
        assert _stored(admin["username"]).used_traffic == 0
    finally:
        _set_stored(owner["username"], role_id=3)
        delete_admin(access_token, owner["username"])
        _cleanup(access_token, role, admin)
