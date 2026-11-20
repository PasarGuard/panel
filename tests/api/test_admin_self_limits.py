"""A limited admin may edit its own profile but must not lift its own limits."""

from fastapi import status

from tests.api import client
from tests.api.helpers import auth_headers, create_admin, delete_admin, unique_name

# What the dashboard admin dialog sends on save when the admin has no overrides.
DASHBOARD_EMPTY_OVERRIDES = {
    "max_users": None,
    "data_limit_min": None,
    "data_limit_max": None,
    "expire_min": None,
    "expire_max": None,
    "min_hwid_per_user": None,
    "max_hwid_per_user": None,
    "on_hold_timeout_min": None,
    "on_hold_timeout_max": None,
}


def _limited_admin(access_token: str) -> tuple[dict, dict, str]:
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("role_self_limits"),
            "permissions": {"admins": {"read": True, "update": True}},
            "limits": {"max_users": 5},
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
    return role, admin, token


def _cleanup(access_token: str, role: dict, admin: dict) -> None:
    delete_admin(access_token, admin["username"])
    client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))


def test_dashboard_save_of_own_profile_without_limit_changes_is_allowed(access_token):
    role, admin, token = _limited_admin(access_token)
    try:
        response = client.put(
            f"/api/admin/by-id/{admin['id']}",
            headers=auth_headers(token),
            json={
                "note": "edited by myself",
                "data_limit": 0,
                "role_id": role["id"],
                "permission_overrides": DASHBOARD_EMPTY_OVERRIDES,
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json()["note"] == "edited by myself"
    finally:
        _cleanup(access_token, role, admin)


def test_limited_admin_cannot_raise_its_own_limits(access_token):
    role, admin, token = _limited_admin(access_token)
    try:
        response = client.put(
            f"/api/admin/by-id/{admin['id']}",
            headers=auth_headers(token),
            json={"permission_overrides": {**DASHBOARD_EMPTY_OVERRIDES, "max_users": 99999}},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN, response.text

        response = client.put(
            f"/api/admin/by-id/{admin['id']}",
            headers=auth_headers(token),
            json={"data_limit": 10 * 1024**4},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN, response.text
    finally:
        _cleanup(access_token, role, admin)


def test_limited_admin_can_resend_unchanged_non_null_override(access_token):
    role, admin, token = _limited_admin(access_token)
    try:
        seed = client.put(
            f"/api/admin/by-id/{admin['id']}",
            headers=auth_headers(access_token),
            json={"permission_overrides": {"max_users": 3}},
        )
        assert seed.status_code == status.HTTP_200_OK, seed.text

        response = client.put(
            f"/api/admin/by-id/{admin['id']}",
            headers=auth_headers(token),
            json={
                "note": "edited by myself",
                "data_limit": 0,
                "role_id": role["id"],
                "permission_overrides": {**DASHBOARD_EMPTY_OVERRIDES, "max_users": 3},
            },
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json()["note"] == "edited by myself"
    finally:
        _cleanup(access_token, role, admin)
