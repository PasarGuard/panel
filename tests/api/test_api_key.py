import asyncio

import pytest
from fastapi import status
from sqlalchemy import select

from app.db.models import Admin, APIKey
from app.models.admin import hash_password
from tests.api import TestSession, client
from tests.api.helpers import auth_headers, create_admin, delete_admin, strong_password, unique_name


def _login(username: str, password: str) -> str:
    response = client.post(
        "/api/admin/token",
        data={"username": username, "password": password, "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()["access_token"]


def _api_key_state(key_id: int) -> tuple[str | None, str]:
    async def _get_state():
        async with TestSession() as session:
            result = await session.execute(select(APIKey).where(APIKey.id == key_id))
            db_key = result.scalar_one()
            revoked_at = db_key.revoked_at.isoformat() if db_key.revoked_at else None
            return revoked_at, db_key.status.value

    return asyncio.run(_get_state())


def _api_key_exists(key_id: int) -> bool:
    async def _exists() -> bool:
        async with TestSession() as session:
            result = await session.execute(select(APIKey.id).where(APIKey.id == key_id))
            return result.scalar_one_or_none() is not None

    return asyncio.run(_exists())


def _create_owner_admin() -> dict:
    username = unique_name("api_key_owner")
    password = strong_password("ApiKeyOwner")

    async def _create_owner() -> int:
        async with TestSession() as session:
            db_admin = Admin(username=username, hashed_password=await hash_password(password), role_id=1)
            session.add(db_admin)
            await session.commit()
            await session.refresh(db_admin)
            return db_admin.id

    return {"id": asyncio.run(_create_owner()), "username": username, "password": password}


def _delete_admin_row(username: str) -> None:
    async def _delete_admin() -> None:
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.username == username))
            db_admin = result.scalar_one_or_none()
            if db_admin is not None:
                await session.delete(db_admin)
                await session.commit()

    asyncio.run(_delete_admin())


def test_api_key_authenticates_protected_requests(access_token):
    admin = create_admin(access_token, role_id=2)
    admin_token = _login(admin["username"], admin["password"])

    try:
        create_response = client.post(
            "/api/api_key",
            headers=auth_headers(admin_token),
            json={"name": unique_name("api_key"), "role_id": 2},
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        created = create_response.json()
        raw_api_key = created["api_key"]

        current_admin_response = client.get("/api/admin", headers={"X-Api-Key": raw_api_key})
        assert current_admin_response.status_code == status.HTTP_200_OK
        assert current_admin_response.json()["username"] == admin["username"]

        list_response = client.get("/api/api_keys", headers={"X-Api-Key": raw_api_key})
        assert list_response.status_code == status.HTTP_200_OK
        listed = list_response.json()
        assert listed["total"] >= 1
        assert any(api_key["id"] == created["id"] for api_key in listed["api_keys"])

        detail_response = client.get(
            f"/api/api_key/{created['id']}",
            headers={"Authorization": f"ApiKey {raw_api_key}"},
        )
        assert detail_response.status_code == status.HTTP_200_OK
        detail = detail_response.json()
        assert detail["id"] == created["id"]
        assert detail["admin_id"] == admin["id"]
        assert "api_key" not in detail

        username = unique_name("api_key_user")
        create_user_response = client.post(
            "/api/user",
            headers={"X-Api-Key": raw_api_key},
            json={
                "username": username,
                "proxy_settings": {},
                "data_limit": 1024 * 1024,
                "data_limit_reset_strategy": "no_reset",
                "status": "active",
            },
        )
        assert create_user_response.status_code == status.HTTP_201_CREATED
        user = create_user_response.json()
        assert user["username"] == username
        assert user["admin"]["username"] == admin["username"]

        delete_user_response = client.delete(
            f"/api/user/{username}",
            headers={"Authorization": f"ApiKey {raw_api_key}"},
        )
        assert delete_user_response.status_code == status.HTTP_204_NO_CONTENT

        delete_again_response = client.delete(
            f"/api/user/{username}",
            headers={"Authorization": f"ApiKey {raw_api_key}"},
        )
        assert delete_again_response.status_code == status.HTTP_404_NOT_FOUND
    finally:
        delete_admin(access_token, admin["username"])


def test_admin_delete_removes_owned_api_keys(access_token):
    admin = create_admin(access_token, role_id=2)
    admin_token = _login(admin["username"], admin["password"])

    create_response = client.post(
        "/api/api_key",
        headers=auth_headers(admin_token),
        json={"name": unique_name("api_key")},
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    key_id = create_response.json()["id"]
    assert _api_key_exists(key_id)

    delete_admin(access_token, admin["username"])

    assert not _api_key_exists(key_id)


def test_revoke_api_key_rotates_secret_and_blocks_old_key(access_token):
    admin = create_admin(access_token, role_id=2)
    admin_token = _login(admin["username"], admin["password"])

    try:
        create_response = client.post(
            "/api/api_key",
            headers=auth_headers(admin_token),
            json={"name": unique_name("api_key"), "role_id": 2},
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        created = create_response.json()
        raw_api_key = created["api_key"]
        assert created["revoked_at"] is None
        assert created["status"] == "active"

        auth_response = client.get("/api/admin", headers={"X-Api-Key": raw_api_key})
        assert auth_response.status_code == status.HTTP_200_OK
        assert auth_response.json()["username"] == admin["username"]

        revoke_response = client.post(f"/api/api_key/{created['id']}/revoke", headers=auth_headers(admin_token))
        assert revoke_response.status_code == status.HTTP_200_OK
        revoked = revoke_response.json()
        new_api_key = revoked["api_key"]
        assert new_api_key != raw_api_key
        assert revoked["id"] == created["id"]
        assert revoked["revoked_at"] is not None
        assert revoked["status"] == "active"

        db_revoked_at, db_status = _api_key_state(created["id"])
        assert db_revoked_at is not None
        assert db_status == "active"

        revoked_auth_response = client.get("/api/admin", headers={"X-Api-Key": raw_api_key})
        assert revoked_auth_response.status_code == status.HTTP_401_UNAUTHORIZED

        new_auth_response = client.get("/api/admin", headers={"X-Api-Key": new_api_key})
        assert new_auth_response.status_code == status.HTTP_200_OK
        assert new_auth_response.json()["username"] == admin["username"]
    finally:
        delete_admin(access_token, admin["username"])


def test_owner_can_assign_api_key_to_admin(access_token):
    owner = _create_owner_admin()
    admin = create_admin(access_token, role_id=2)
    owner_token = _login(owner["username"], owner["password"])

    try:
        create_response = client.post(
            "/api/api_key",
            headers=auth_headers(owner_token),
            json={"name": unique_name("api_key"), "admin_id": admin["id"]},
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        created = create_response.json()
        raw_api_key = created["api_key"]
        assert created["admin_id"] == admin["id"]

        current_admin_response = client.get("/api/admin", headers={"X-Api-Key": raw_api_key})
        assert current_admin_response.status_code == status.HTTP_200_OK
        assert current_admin_response.json()["username"] == admin["username"]
    finally:
        delete_admin(access_token, admin["username"])
        _delete_admin_row(owner["username"])


def test_bulk_delete_api_keys_removes_selected_keys(access_token):
    owner = _create_owner_admin()
    owner_token = _login(owner["username"], owner["password"])

    first_response = client.post(
        "/api/api_key",
        headers=auth_headers(owner_token),
        json={"name": unique_name("api_key")},
    )
    second_response = client.post(
        "/api/api_key",
        headers=auth_headers(owner_token),
        json={"name": unique_name("api_key")},
    )
    try:
        assert first_response.status_code == status.HTTP_201_CREATED
        assert second_response.status_code == status.HTTP_201_CREATED
        first = first_response.json()
        second = second_response.json()

        delete_response = client.post(
            "/api/api_keys/bulk/delete",
            headers=auth_headers(owner_token),
            json={"ids": [first["id"], second["id"]]},
        )

        assert delete_response.status_code == status.HTTP_200_OK
        deleted = delete_response.json()
        assert deleted["count"] == 2
        assert set(deleted["api_keys"]) == {first["name"], second["name"]}

        for key_id in (first["id"], second["id"]):
            detail_response = client.get(f"/api/api_key/{key_id}", headers=auth_headers(owner_token))
            assert detail_response.status_code == status.HTTP_404_NOT_FOUND
    finally:
        _delete_admin_row(owner["username"])


def test_bulk_delete_api_keys_rejects_missing_key(access_token):
    delete_response = client.post(
        "/api/api_keys/bulk/delete",
        headers=auth_headers(access_token),
        json={"ids": [999999999]},
    )

    assert delete_response.status_code == status.HTTP_404_NOT_FOUND


def test_api_key_create_permission_rejects_scope(access_token):
    create_response = client.post(
        "/api/api_key",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("api_key"),
            "inherit_permissions": False,
            "permissions": {
                "api_keys": {
                    "create": {"scope": 2},
                    "read": {"scope": 2},
                }
            },
        },
    )

    assert create_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_non_owner_cannot_assign_api_key_to_other_admin(access_token):
    admin = create_admin(access_token, role_id=2)
    other_admin = create_admin(access_token, role_id=2)
    admin_token = _login(admin["username"], admin["password"])

    try:
        create_response = client.post(
            "/api/api_key",
            headers=auth_headers(admin_token),
            json={"name": unique_name("api_key"), "admin_id": other_admin["id"]},
        )
        assert create_response.status_code == status.HTTP_403_FORBIDDEN
    finally:
        delete_admin(access_token, admin["username"])
        delete_admin(access_token, other_admin["username"])


_KEY_ADMIN_PERMISSIONS = {
    "create": True,
    "read": {"scope": 2},
    "update": {"scope": 2},
    "delete": {"scope": 2},
}


def _key_headers(raw_key: str) -> dict[str, str]:
    return {"X-Api-Key": raw_key}


def _create_key(headers: dict[str, str], *, permissions: dict | None = None) -> dict:
    payload = {"name": unique_name("api_key"), "inherit_permissions": permissions is None}
    if permissions is not None:
        payload["permissions"] = permissions
    response = client.post("/api/api_key", headers=headers, json=payload)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


def test_custom_key_cannot_mint_or_become_inheriting_key():
    owner = _create_owner_admin()
    try:
        owner_headers = auth_headers(_login(owner["username"], owner["password"]))
        restricted = _create_key(
            owner_headers, permissions={"users": {"read": {"scope": 2}}, "api_keys": _KEY_ADMIN_PERMISSIONS}
        )
        restricted_headers = _key_headers(restricted["api_key"])
        assert client.get("/api/admin-roles", headers=restricted_headers).status_code == status.HTTP_403_FORBIDDEN

        response = client.post(
            "/api/api_key",
            headers=restricted_headers,
            json={"name": unique_name("escalated"), "inherit_permissions": True},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        response = client.patch(
            f"/api/api_key/{restricted['id']}", headers=restricted_headers, json={"inherit_permissions": True}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # A narrower custom key it minted itself cannot be switched to inheriting either.
        minted = _create_key(restricted_headers, permissions={"users": {"read": {"scope": 2}}})
        response = client.patch(
            f"/api/api_key/{minted['id']}", headers=restricted_headers, json={"inherit_permissions": True}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert client.get("/api/admin-roles", headers=_key_headers(minted["api_key"])).status_code == 403
    finally:
        _delete_admin_row(owner["username"])


def test_custom_key_cannot_rotate_broader_key():
    owner = _create_owner_admin()
    try:
        owner_headers = auth_headers(_login(owner["username"], owner["password"]))
        inheriting = _create_key(owner_headers)
        broader = _create_key(owner_headers, permissions={"admins": {"read": True}, "api_keys": _KEY_ADMIN_PERMISSIONS})
        restricted = _create_key(owner_headers, permissions={"api_keys": _KEY_ADMIN_PERMISSIONS})
        restricted_headers = _key_headers(restricted["api_key"])

        for target in (inheriting, broader):
            response = client.post(f"/api/api_key/{target['id']}/revoke", headers=restricted_headers)
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert "api_key" not in response.json()
        # the rejected rotations left both keys working
        assert client.get("/api/admin-roles", headers=_key_headers(inheriting["api_key"])).status_code == 200
        assert client.get("/api/admins", headers=_key_headers(broader["api_key"])).status_code == 200
    finally:
        _delete_admin_row(owner["username"])


def _create_scoped_key_admin(access_token: str) -> tuple[dict, int]:
    response = client.post(
        "/api/admin-role",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("scoped_key_role"),
            "permissions": {
                "users": {"create": True, "read": {"scope": 1}},
                "api_keys": _KEY_ADMIN_PERMISSIONS,
            },
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    role_id = response.json()["id"]
    return create_admin(access_token, role_id=role_id), role_id


@pytest.mark.parametrize("kind", ["owner", "administrator", "scoped"])
def test_session_and_keys_still_manage_keys_within_their_permissions(access_token, kind):
    role_id = None
    if kind == "owner":
        admin = _create_owner_admin()
    elif kind == "administrator":
        admin = create_admin(access_token, role_id=2)
    else:
        admin, role_id = _create_scoped_key_admin(access_token)
    narrow = {"api_keys": _KEY_ADMIN_PERMISSIONS}
    try:
        session_headers = auth_headers(_login(admin["username"], admin["password"]))
        # sessions and inheriting keys keep minting, editing and rotating inheriting keys
        inheriting = _create_key(session_headers)
        inheriting_headers = _key_headers(inheriting["api_key"])
        second = _create_key(inheriting_headers)
        response = client.patch(f"/api/api_key/{second['id']}", headers=inheriting_headers, json={"note": "edited"})
        assert response.status_code == status.HTTP_200_OK
        response = client.post(f"/api/api_key/{second['id']}/revoke", headers=inheriting_headers)
        assert response.status_code == status.HTTP_200_OK
        assert client.get("/api/api_keys", headers=_key_headers(response.json()["api_key"])).status_code == 200

        # custom keys keep minting, editing and rotating custom keys within their own permissions
        custom = _create_key(inheriting_headers, permissions=narrow)
        custom_headers = _key_headers(custom["api_key"])
        sibling = _create_key(custom_headers, permissions=narrow)
        response = client.patch(f"/api/api_key/{sibling['id']}", headers=custom_headers, json={"note": "edited"})
        assert response.status_code == status.HTTP_200_OK
        response = client.post(f"/api/api_key/{sibling['id']}/revoke", headers=custom_headers)
        assert response.status_code == status.HTTP_200_OK
        response = client.patch(f"/api/api_key/{custom['id']}", headers=custom_headers, json={"note": "self"})
        assert response.status_code == status.HTTP_200_OK
        response = client.post(f"/api/api_key/{custom['id']}/revoke", headers=custom_headers)
        assert response.status_code == status.HTTP_200_OK
        assert client.get("/api/api_keys", headers=_key_headers(response.json()["api_key"])).status_code == 200
    finally:
        if kind == "owner":
            _delete_admin_row(admin["username"])
        else:
            delete_admin(access_token, admin["username"])
        if role_id is not None:
            client.delete(f"/api/admin-role/{role_id}", headers=auth_headers(access_token))
