"""Regression tests for RBAC permission leaks."""

import asyncio

from fastapi import status
from sqlalchemy import select

from app.db.models import Admin
from app.models.admin import hash_password
from tests.api import TestSession, client
from tests.api.helpers import (
    auth_headers,
    create_admin,
    delete_admin,
    strong_password,
    unique_name,
)


def _login(username: str, password: str) -> str:
    response = client.post(
        "/api/admin/token",
        data={"username": username, "password": password, "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()["access_token"]


def _create_owner_admin() -> dict:
    username = unique_name("owner_key")
    password = strong_password("OwnerKey")

    async def _create() -> int:
        async with TestSession() as session:
            db_admin = Admin(username=username, hashed_password=await hash_password(password), role_id=1)
            session.add(db_admin)
            await session.commit()
            await session.refresh(db_admin)
            return db_admin.id

    return {"id": asyncio.run(_create()), "username": username, "password": password}


def _delete_admin_row(username: str) -> None:
    async def _delete() -> None:
        async with TestSession() as session:
            db_admin = (await session.execute(select(Admin).where(Admin.username == username))).scalar_one_or_none()
            if db_admin is not None:
                await session.delete(db_admin)
                await session.commit()

    asyncio.run(_delete())


def _create_api_key(token: str, **payload) -> str:
    response = client.post(
        "/api/api_key",
        headers=auth_headers(token),
        json={"name": unique_name("api_key"), **payload},
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()["api_key"]


# --- API keys with custom (non-inherited) permissions ---


def test_api_key_with_empty_custom_permissions_grants_nothing(access_token):
    admin = create_admin(access_token, role_id=2)
    try:
        raw_key = _create_api_key(
            _login(admin["username"], admin["password"]),
            inherit_permissions=False,
            permissions={},
        )

        response = client.get("/api/users", headers={"X-Api-Key": raw_key})

        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, admin["username"])


def test_owner_api_key_with_empty_custom_permissions_is_not_owner(access_token):
    owner = _create_owner_admin()
    try:
        raw_key = _create_api_key(
            _login(owner["username"], owner["password"]),
            inherit_permissions=False,
            permissions={},
        )

        response = client.get("/api/admin-roles", headers={"X-Api-Key": raw_key})

        assert response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        _delete_admin_row(owner["username"])
