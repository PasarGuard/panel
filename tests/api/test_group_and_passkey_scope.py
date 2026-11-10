"""Bulk group changes follow users.update and its scope; the owner's passkeys stay with the owner."""

import asyncio

from fastapi import status
from sqlalchemy import select

from app.db.models import Admin
from app.models.admin import hash_password
from tests.api import TestSession, client
from tests.api.helpers import (
    auth_headers,
    create_admin,
    create_core,
    create_group,
    create_user,
    delete_admin,
    strong_password,
    unique_name,
)


def _role(access_token: str, permissions: dict, limits: dict | None = None) -> dict:
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("role_regression"),
            "permissions": permissions,
            "limits": limits or {},
            "features": {},
            "access": {},
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def _actor(access_token: str, permissions: dict, limits: dict | None = None) -> tuple[dict, dict, str]:
    role = _role(access_token, permissions, limits)
    admin = create_admin(access_token, role_id=role["id"])
    token = client.post(
        "/api/admin/token",
        data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
    ).json()["access_token"]
    return role, admin, token


def _drop_actor(access_token: str, role: dict, admin: dict) -> None:
    delete_admin(access_token, admin["username"])
    client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))


def _user_group_ids(access_token: str, user_id: int) -> list[int]:
    response = client.get(f"/api/user/by-id/{user_id}", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()["group_ids"]


# Bulk group changes respect users.update and its scope


def test_bulk_group_add_requires_users_update_and_keeps_its_scope(access_token):
    core = create_core(access_token)
    group = create_group(access_token, name=unique_name("regression_group"))
    target_user = create_user(access_token)
    only_groups = _actor(access_token, {"groups": {"read": True, "update": True}})
    own_users = _actor(
        access_token,
        {"groups": {"read": True, "update": True}, "users": {"read": {"scope": 1}, "update": {"scope": 1}}},
    )
    try:
        body = {"group_ids": [group["id"]], "users": [target_user["id"]]}

        response = client.post("/api/groups/bulk/add", headers=auth_headers(only_groups[2]), json=body)
        assert response.status_code == status.HTTP_403_FORBIDDEN, response.text

        response = client.post("/api/groups/bulk/add", headers=auth_headers(own_users[2]), json=body)
        assert response.status_code == status.HTTP_200_OK, response.text
        assert group["id"] not in _user_group_ids(access_token, target_user["id"])

        response = client.post(
            "/api/groups/bulk/add", headers=auth_headers(own_users[2]), json={**body, "dry_run": True}
        )
        assert response.json()["affected_users"] == 0
    finally:
        _drop_actor(access_token, *only_groups[:2])
        _drop_actor(access_token, *own_users[:2])
        client.delete(f"/api/user/by-id/{target_user['id']}", headers=auth_headers(access_token))
        client.delete(f"/api/group/{group['id']}", headers=auth_headers(access_token))
        client.delete(f"/api/core/{core['id']}", headers=auth_headers(access_token))


# The owner's passkeys are out of reach of admins.passkeys


def _owner_row() -> dict:
    username = unique_name("owner_passkeys")

    async def _create():
        async with TestSession() as session:
            owner = Admin(username=username, hashed_password=await hash_password(strong_password("Owner")), role_id=1)
            session.add(owner)
            await session.commit()
            return owner.id

    return {"id": asyncio.run(_create()), "username": username}


def _delete_admin_row(username: str) -> None:
    async def _delete():
        async with TestSession() as session:
            row = (await session.execute(select(Admin).where(Admin.username == username))).scalar_one_or_none()
            if row is not None:
                await session.delete(row)
                await session.commit()

    asyncio.run(_delete())


def test_admins_passkeys_permission_cannot_touch_owner_passkeys(access_token):
    owner = _owner_row()
    role, admin, token = _actor(access_token, {"admins": {"read": True, "passkeys": True}})
    other = create_admin(access_token)
    try:
        assert client.get(f"/api/admin/passkey/admins/{owner['id']}", headers=auth_headers(token)).status_code == 403
        assert (
            client.delete(f"/api/admin/passkey/admins/{owner['id']}/1", headers=auth_headers(token)).status_code == 403
        )
        response = client.post(f"/api/admin/passkey/admins/{owner['id']}/register/options", headers=auth_headers(token))
        assert response.status_code == 403
        # The permission still works for a regular admin.
        assert client.get(f"/api/admin/passkey/admins/{other['id']}", headers=auth_headers(token)).status_code == 200
    finally:
        _drop_actor(access_token, role, admin)
        delete_admin(access_token, other["username"])
        _delete_admin_row(owner["username"])
