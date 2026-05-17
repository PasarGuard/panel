"""
Tests for /api/setup endpoints (owner create / reset / delete via temp key).
"""

import asyncio
from datetime import datetime, timedelta, timezone

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
                expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
            else:
                expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

            key = TempKey(
                key=__import__("uuid").uuid4().__str__(),
                action="setup",
                expires_at=expires_at,
                used_at=datetime.now(timezone.utc) if used else None,
                used_by_ip="127.0.0.1" if used else None,
            )
            session.add(key)
            await session.commit()
            return key.key

    return asyncio.run(_insert())


def _delete_owner() -> None:
    """Remove the owner admin (role_id=1) if it exists."""

    async def _remove():
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.role_id == 1))
            owner = result.scalar_one_or_none()
            if owner:
                await session.delete(owner)
                await session.commit()

    asyncio.run(_remove())


def _owner_exists() -> bool:
    async def _check():
        async with TestSession() as session:
            result = await session.execute(select(Admin).where(Admin.role_id == 1))
            return result.scalar_one_or_none() is not None

    return asyncio.run(_check())


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
        assert data["is_sudo"] is True
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
            json={"key": delete_key},
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
        json={"key": key},
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
        json={"key": key},
    )
    assert response.status_code == status.HTTP_410_GONE


def test_already_used_key_returns_410_on_delete():
    """Already-used key returns 410 on DELETE /api/setup/owner."""
    key = _make_temp_key(used=True)
    response = client.request(
        "DELETE",
        "/api/setup/owner",
        json={"key": key},
    )
    assert response.status_code == status.HTTP_410_GONE


def test_invalid_key_returns_400_on_delete():
    """Invalid/unknown key returns 400 on DELETE /api/setup/owner."""
    response = client.request(
        "DELETE",
        "/api/setup/owner",
        json={"key": "00000000-0000-0000-0000-000000000002"},
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
