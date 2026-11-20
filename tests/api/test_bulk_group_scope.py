"""Bulk group changes follow users.update and its scope."""

from fastapi import status

from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_admin,
    create_core,
    create_group,
    create_user,
    delete_admin,
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
