"""
Tests for /api/setup endpoints (owner create / reset / delete via temp key).
"""

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy import select

from app.db.models import Admin, TempKey
from tests.api import TestSession, client

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_temp_key(*, used: bool = False, expired: bool = False) -> str:
    """Insert a TempKey directly into the DB and return its key string."""

    async def _insert():
        async with TestSession() as session:
            if expired:
                expires_at = datetime.now(UTC) - timedelta(minutes=10)
            else:
                expires_at = datetime.now(UTC) + timedelta(minutes=5)

            key = TempKey(
                key=__import__("uuid").uuid4().__str__(),
                action="setup",
                expires_at=expires_at,
                used_at=datetime.now(UTC) if used else None,
                used_by_ip="127.0.0.1" if used else None,
            )
            session.add(key)
            await session.commit()
            return key.key

    return asyncio.run(_insert())


def _delete_owner() -> None:
    """Remove all owner admins (role_id=1) if any exist."""

    async def _remove():
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.role_id == 1))
            owners = result.scalars().all()
            for owner in owners:
                await session.delete(owner)
            if owners:
                await session.commit()

    asyncio.run(_remove())


def _owner_exists() -> bool:
    async def _check():
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.role_id == 1))
            return result.scalar_one_or_none() is not None

    return asyncio.run(_check())


def _create_admin(username: str, role_id: int = 2) -> None:
    """Create an admin directly in DB for setup-route tests."""

    async def _insert():
        async with TestSession() as session:
            admin = Admin(
                username=username,
                hashed_password="$2b$12$dummyhashdummyhashdummyhashdummyhashdummyhashd",
                role_id=role_id,
            )
            session.add(admin)
            await session.commit()

    asyncio.run(_insert())


def _delete_admin_by_username(username: str) -> None:
    async def _delete():
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.username == username))
            admin = result.scalar_one_or_none()
            if admin:
                await session.delete(admin)
                await session.commit()

    asyncio.run(_delete())


def _owner_usernames() -> list[str]:
    async def _fetch() -> list[str]:
        async with TestSession() as session:
            result = await session.execute(select(Admin.username).where(Admin.role_id == 1))
            return list(result.scalars().all())

    return asyncio.run(_fetch())


# ---------------------------------------------------------------------------
# POST /api/setup/owner — create owner
# ---------------------------------------------------------------------------


def test_create_owner_success():
    """Valid key creates owner successfully."""
    key = _make_temp_key()
    try:
        response = client.post(
            "/api/setup/owner",
            json={"key": key, "username": "owner_user", "password": "OwnerPass#12ab"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["username"] == "owner_user"
        # Owner role has is_owner=True in the role object
        assert data["role"]["is_owner"] is True
    finally:
        _delete_owner()


def test_create_owner_already_exists_returns_409():
    """Creating owner when one already exists returns 409."""
    key1 = _make_temp_key()
    key2 = _make_temp_key()
    try:
        # Create the owner first
        r1 = client.post(
            "/api/setup/owner",
            json={"key": key1, "username": "owner_first", "password": "OwnerPass#12ab"},
        )
        assert r1.status_code == status.HTTP_201_CREATED

        # Try to create again
        r2 = client.post(
            "/api/setup/owner",
            json={"key": key2, "username": "owner_second", "password": "OwnerPass#12ab"},
        )
        assert r2.status_code == status.HTTP_409_CONFLICT
    finally:
        _delete_owner()


# ---------------------------------------------------------------------------
# PATCH /api/setup/owner — reset owner password
# ---------------------------------------------------------------------------


def test_create_owner_weak_password_returns_422():
    """Weak owner password is rejected during request validation."""
    key = _make_temp_key()
    response = client.post(
        "/api/setup/owner",
        json={"key": key, "username": "owner_weak", "password": "2250Na@"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Password must contain at least 2 uppercase letters" in response.text
    assert not _owner_exists()


def test_reset_owner_password_success():
    """Valid key resets owner password."""
    create_key = _make_temp_key()
    reset_key = _make_temp_key()
    try:
        # Create owner first
        r1 = client.post(
            "/api/setup/owner",
            json={"key": create_key, "username": "owner_reset", "password": "OwnerPass#12ab"},
        )
        assert r1.status_code == status.HTTP_201_CREATED

        # Reset password
        r2 = client.patch(
            "/api/setup/owner",
            json={"key": reset_key, "password": "NewOwnerPass#34cd"},
        )
        assert r2.status_code == status.HTTP_200_OK
        data = r2.json()
        assert data["username"] == "owner_reset"
    finally:
        _delete_owner()


def test_reset_owner_password_no_owner_returns_404():
    """Resetting password when no owner exists returns 404."""
    key = _make_temp_key()
    _delete_owner()  # ensure no owner

    response = client.patch(
        "/api/setup/owner",
        json={"key": key, "password": "NewOwnerPass#34cd"},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# DELETE /api/setup/owner — delete owner
# ---------------------------------------------------------------------------


def test_reset_owner_weak_password_returns_422():
    """Weak owner reset password is rejected during request validation."""
    create_key = _make_temp_key()
    reset_key = _make_temp_key()
    try:
        r1 = client.post(
            "/api/setup/owner",
            json={"key": create_key, "username": "owner_reset_weak", "password": "OwnerPass#12ab"},
        )
        assert r1.status_code == status.HTTP_201_CREATED

        response = client.patch(
            "/api/setup/owner",
            json={"key": reset_key, "password": "2250Na@"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Password must contain at least 2 uppercase letters" in response.text
    finally:
        _delete_owner()


def test_delete_owner_success():
    """Valid key deletes owner."""
    create_key = _make_temp_key()
    delete_key = _make_temp_key()
    try:
        # Create owner first
        r1 = client.post(
            "/api/setup/owner",
            json={"key": create_key, "username": "owner_del", "password": "OwnerPass#12ab"},
        )
        assert r1.status_code == status.HTTP_201_CREATED

        # Delete owner
        r2 = client.request(
            "DELETE",
            "/api/setup/owner",
            params={"key": delete_key},
        )
        assert r2.status_code == status.HTTP_204_NO_CONTENT
        assert not _owner_exists()
    finally:
        _delete_owner()


def test_delete_owner_no_owner_returns_404():
    """Deleting owner when none exists returns 404."""
    key = _make_temp_key()
    _delete_owner()  # ensure no owner

    response = client.request(
        "DELETE",
        "/api/setup/owner",
        params={"key": key},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Key validation — shared across all three endpoints
# ---------------------------------------------------------------------------


def test_expired_key_returns_410_on_create():
    """Expired key returns 410 on POST /api/setup/owner."""
    key = _make_temp_key(expired=True)
    response = client.post(
        "/api/setup/owner",
        json={"key": key, "username": "owner_exp", "password": "OwnerPass#12ab"},
    )
    assert response.status_code == status.HTTP_410_GONE
    assert response.json()["detail"] == "key expired"


def test_already_used_key_returns_410_on_create():
    """Already-used key returns 410 on POST /api/setup/owner."""
    key = _make_temp_key(used=True)
    response = client.post(
        "/api/setup/owner",
        json={"key": key, "username": "owner_used", "password": "OwnerPass#12ab"},
    )
    assert response.status_code == status.HTTP_410_GONE
    assert response.json()["detail"] == "key already used"


def test_invalid_key_returns_400_on_create():
    """Invalid/unknown key returns 400 on POST /api/setup/owner."""
    response = client.post(
        "/api/setup/owner",
        json={"key": "00000000-0000-0000-0000-000000000000", "username": "owner_inv", "password": "OwnerPass#12ab"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "invalid key"


def test_expired_key_returns_410_on_reset():
    """Expired key returns 410 on PATCH /api/setup/owner."""
    key = _make_temp_key(expired=True)
    response = client.patch(
        "/api/setup/owner",
        json={"key": key, "password": "NewOwnerPass#34cd"},
    )
    assert response.status_code == status.HTTP_410_GONE


def test_already_used_key_returns_410_on_reset():
    """Already-used key returns 410 on PATCH /api/setup/owner."""
    key = _make_temp_key(used=True)
    response = client.patch(
        "/api/setup/owner",
        json={"key": key, "password": "NewOwnerPass#34cd"},
    )
    assert response.status_code == status.HTTP_410_GONE


def test_invalid_key_returns_400_on_reset():
    """Invalid/unknown key returns 400 on PATCH /api/setup/owner."""
    response = client.patch(
        "/api/setup/owner",
        json={"key": "00000000-0000-0000-0000-000000000001", "password": "NewOwnerPass#34cd"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_expired_key_returns_410_on_delete():
    """Expired key returns 410 on DELETE /api/setup/owner."""
    key = _make_temp_key(expired=True)
    response = client.request(
        "DELETE",
        "/api/setup/owner",
        params={"key": key},
    )
    assert response.status_code == status.HTTP_410_GONE


def test_already_used_key_returns_410_on_delete():
    """Already-used key returns 410 on DELETE /api/setup/owner."""
    key = _make_temp_key(used=True)
    response = client.request(
        "DELETE",
        "/api/setup/owner",
        params={"key": key},
    )
    assert response.status_code == status.HTTP_410_GONE


def test_invalid_key_returns_400_on_delete():
    """Invalid/unknown key returns 400 on DELETE /api/setup/owner."""
    response = client.request(
        "DELETE",
        "/api/setup/owner",
        params={"key": "00000000-0000-0000-0000-000000000002"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# Key is consumed after successful operation
# ---------------------------------------------------------------------------


def test_key_is_consumed_after_create():
    """After a successful create, the key is marked as used."""
    key = _make_temp_key()
    try:
        r = client.post(
            "/api/setup/owner",
            json={"key": key, "username": "owner_consume", "password": "OwnerPass#12ab"},
        )
        assert r.status_code == status.HTTP_201_CREATED

        # Trying to use the same key again should return 410
        r2 = client.patch(
            "/api/setup/owner",
            json={"key": key, "password": "AnotherPass#56ef"},
        )
        assert r2.status_code == status.HTTP_410_GONE
        assert r2.json()["detail"] == "key already used"
    finally:
        _delete_owner()


# ---------------------------------------------------------------------------
# POST /api/setup/owner/upgrade — upgrade existing admin to owner
# ---------------------------------------------------------------------------


def test_upgrade_owner_rejects_when_owner_exists():
    create_key = _make_temp_key()
    upgrade_key = _make_temp_key()
    try:
        r1 = client.post(
            "/api/setup/owner",
            json={"key": create_key, "username": "owner_before_upgrade", "password": "OwnerPass#12ab"},
        )
        assert r1.status_code == status.HTTP_201_CREATED

        _create_admin("admin_to_upgrade", role_id=2)

        r2 = client.post(
            "/api/setup/owner/upgrade",
            json={"key": upgrade_key, "username": "admin_to_upgrade"},
        )
        assert r2.status_code == status.HTTP_409_CONFLICT
        assert r2.json()["detail"] == "owner already exists"

        owners = _owner_usernames()
        assert owners == ["owner_before_upgrade"]
    finally:
        _delete_owner()
        _delete_admin_by_username("owner_before_upgrade")
        _delete_admin_by_username("admin_to_upgrade")


def test_upgrade_owner_success_when_no_current_owner():
    _delete_owner()
    _create_admin("admin_becomes_owner", role_id=2)
    upgrade_key = _make_temp_key()
    try:
        r = client.post(
            "/api/setup/owner/upgrade",
            json={"key": upgrade_key, "username": "admin_becomes_owner"},
        )
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert data["username"] == "admin_becomes_owner"
        assert data["role"]["is_owner"] is True

        owners = _owner_usernames()
        assert owners == ["admin_becomes_owner"]
    finally:
        _delete_owner()
        _delete_admin_by_username("admin_becomes_owner")


def test_upgrade_owner_target_admin_not_found_returns_404():
    key = _make_temp_key()
    response = client.post(
        "/api/setup/owner/upgrade",
        json={"key": key, "username": "admin_missing_for_upgrade"},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_upgrade_owner_multiple_owners_returns_409():
    create_key = _make_temp_key()
    upgrade_key = _make_temp_key()
    try:
        r1 = client.post(
            "/api/setup/owner",
            json={"key": create_key, "username": "owner_a", "password": "OwnerPass#12ab"},
        )
        assert r1.status_code == status.HTTP_201_CREATED

        _create_admin("owner_b", role_id=1)
        _create_admin("admin_target", role_id=2)

        r2 = client.post(
            "/api/setup/owner/upgrade",
            json={"key": upgrade_key, "username": "admin_target"},
        )
        assert r2.status_code == status.HTTP_409_CONFLICT
        assert r2.json()["detail"] == "owner already exists"
    finally:
        _delete_owner()
        _delete_admin_by_username("owner_a")
        _delete_admin_by_username("owner_b")
        _delete_admin_by_username("admin_target")
