import asyncio

from fastapi import status
from sqlalchemy import select

from app.db.models import APIKey
from tests.api import TestSession, client
from tests.api.helpers import auth_headers, create_admin, delete_admin, unique_name


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
