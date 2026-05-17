"""Tests for /api/admin-role endpoints (owner-only role management)."""

import asyncio

from fastapi import status
from sqlalchemy import select

from app.db.models import Admin
from app.models.admin import hash_password as _hash_password
from tests.api import client, TestSession
from tests.api.helpers import auth_headers, unique_name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _role_payload(name: str | None = None) -> dict:
    return {
        "name": name or unique_name("role"),
        "permissions": {},
        "limits": {
            "max_users": None,
            "data_limit_min": None,
            "data_limit_max": None,
            "expire_days_min": None,
            "expire_days_max": None,
            "max_hwid_per_user": None,
        },
        "features": {"can_use_reset_strategy": True, "can_use_next_plan": True},
        "access": {"require_template": False, "allowed_template_ids": None, "allowed_group_ids": None},
    }


def _create_role(access_token: str, name: str | None = None) -> dict:
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json=_role_payload(name),
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def _delete_role(access_token: str, role_id: int) -> None:
    client.delete(f"/api/admin-role/{role_id}", headers=auth_headers(access_token))


# ---------------------------------------------------------------------------
# GET /api/admin-roles
# ---------------------------------------------------------------------------


def test_get_roles_returns_list(access_token):
    """Owner can list all roles."""
    response = client.get("/api/admin-roles", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "roles" in data
    assert "total" in data
    assert data["total"] >= 3  # owner, administrator, operator seeded by migration


def test_get_roles_simple(access_token):
    """Owner can get lightweight role list."""
    response = client.get("/api/admin-roles/simple", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "roles" in data
    for role in data["roles"]:
        assert "id" in role
        assert "name" in role
        assert "is_owner" in role


# ---------------------------------------------------------------------------
# GET /api/admin-role/{id}
# ---------------------------------------------------------------------------


def test_get_role_by_id(access_token):
    """Owner can fetch a role by ID."""
    response = client.get("/api/admin-role/1", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "owner"
    assert data["is_owner"] is True


def test_get_role_not_found(access_token):
    """Non-existent role returns 404."""
    response = client.get("/api/admin-role/99999", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# POST /api/admin-role
# ---------------------------------------------------------------------------


def test_create_role(access_token):
    """Owner can create a new role."""
    name = unique_name("role")
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json=_role_payload(name),
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == name
    assert data["is_owner"] is False
    _delete_role(access_token, data["id"])


def test_create_role_duplicate_name_returns_409(access_token):
    """Creating a role with a duplicate name returns 409."""
    role = _create_role(access_token)
    try:
        response = client.post(
            "/api/admin-role",
            headers=auth_headers(access_token),
            json=_role_payload(role["name"]),
        )
        assert response.status_code == status.HTTP_409_CONFLICT
    finally:
        _delete_role(access_token, role["id"])


# ---------------------------------------------------------------------------
# PUT /api/admin-role/{id}
# ---------------------------------------------------------------------------


def test_modify_role(access_token):
    """Owner can modify a custom role."""
    role = _create_role(access_token)
    try:
        new_name = unique_name("modified")
        response = client.put(
            f"/api/admin-role/{role['id']}",
            headers=auth_headers(access_token),
            json={"name": new_name},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == new_name
    finally:
        _delete_role(access_token, role["id"])


def test_modify_owner_role_returns_403(access_token):
    """Owner role (id=1) cannot be modified."""
    response = client.put(
        "/api/admin-role/1",
        headers=auth_headers(access_token),
        json={"name": "hacked"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_modify_role_not_found(access_token):
    """Modifying a non-existent role returns 404."""
    response = client.put(
        "/api/admin-role/99999",
        headers=auth_headers(access_token),
        json={"name": "ghost"},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# DELETE /api/admin-role/{id}
# ---------------------------------------------------------------------------


def test_delete_role(access_token):
    """Owner can delete a custom role."""
    role = _create_role(access_token)
    response = client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_204_NO_CONTENT


def test_delete_builtin_role_returns_403(access_token):
    """Built-in roles (1, 2, 3) cannot be deleted."""
    for role_id in (1, 2, 3):
        response = client.delete(f"/api/admin-role/{role_id}", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_403_FORBIDDEN


def test_delete_role_in_use_returns_409(access_token):
    """A role assigned to at least one admin cannot be deleted."""

    role = _create_role(access_token)
    role_id = role["id"]

    # Create a real DB admin assigned to the new role so the in-use guard triggers
    async def _create_test_admin() -> int:
        hashed = await _hash_password("TestPass#99")
        async with TestSession() as session:
            admin = Admin(username=unique_name("roletest"), hashed_password=hashed, role_id=role_id)
            session.add(admin)
            await session.commit()
            return admin.id

    async def _delete_test_admin(admin_id: int) -> None:
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.id == admin_id))
            admin = result.scalar_one_or_none()
            if admin:
                await session.delete(admin)
                await session.commit()

    admin_id = asyncio.run(_create_test_admin())
    try:
        response = client.delete(f"/api/admin-role/{role_id}", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_409_CONFLICT
    finally:
        asyncio.run(_delete_test_admin(admin_id))
        _delete_role(access_token, role_id)


def test_delete_role_not_found(access_token):
    """Deleting a non-existent role returns 404."""
    response = client.delete("/api/admin-role/99999", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_404_NOT_FOUND
