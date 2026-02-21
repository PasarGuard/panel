from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.nats.admin_auth_cache import AdminAuthCacheUnavailableError
from app.models.admin import AdminAuthKVEntry, AdminDetails
from app.routers import authentication
from config import NATS_ENABLED


pytestmark = pytest.mark.skipif(not NATS_ENABLED, reason="NATS auth tests require NATS_ENABLED=1")


def _build_request(method: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
    )


@pytest.mark.asyncio
async def test_get_current_nats_enabled_uses_kv_on_get(monkeypatch):
    now = datetime.now(timezone.utc)

    async def fake_get_payload(_: str):
        return {"username": "admin1", "is_sudo": False, "created_at": now}

    async def fake_get_admin(_: str):
        return AdminAuthKVEntry(
            id=1,
            username="admin1",
            is_sudo=False,
            is_disabled=False,
            password_reset_at=None,
            updated_at=now,
        )

    async def fail_db_lookup(*args, **kwargs):
        raise AssertionError("DB lookup should not be used in GET NATS auth path")

    monkeypatch.setattr(authentication, "get_admin_payload", fake_get_payload)
    monkeypatch.setattr(authentication.admin_auth_cache_service, "get_admin", fake_get_admin)
    monkeypatch.setattr(authentication, "get_admin_by_username", fail_db_lookup)

    admin = await authentication.get_current_nats_enabled(
        request=_build_request("GET"),
        db=AsyncMock(),
        token="token",
    )
    assert admin.username == "admin1"
    assert admin.id == 1


@pytest.mark.asyncio
async def test_get_current_nats_enabled_uses_db_for_non_get(monkeypatch):
    db_admin = AdminDetails(id=9, username="db-admin", is_sudo=False, is_disabled=False)
    get_current_db_mock = AsyncMock(return_value=db_admin)
    monkeypatch.setattr(authentication, "get_current_db", get_current_db_mock)

    db = AsyncMock()
    admin = await authentication.get_current_nats_enabled(request=_build_request("POST"), db=db, token="token")

    assert admin.username == "db-admin"
    get_current_db_mock.assert_awaited_once_with(db=db, token="token")


@pytest.mark.asyncio
async def test_get_current_nats_enabled_fail_closed_when_kv_unavailable(monkeypatch):
    now = datetime.now(timezone.utc)

    async def fake_get_payload(_: str):
        return {"username": "admin2", "is_sudo": False, "created_at": now}

    async def fake_get_admin(_: str):
        raise AdminAuthCacheUnavailableError("missing key")

    monkeypatch.setattr(authentication, "get_admin_payload", fake_get_payload)
    monkeypatch.setattr(authentication.admin_auth_cache_service, "get_admin", fake_get_admin)

    with pytest.raises(HTTPException) as exc_info:
        await authentication.get_current_nats_enabled(
            request=_build_request("GET"),
            db=AsyncMock(),
            token="token",
        )

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_get_current_nats_enabled_rejects_token_after_password_reset(monkeypatch):
    now = datetime.now(timezone.utc)
    token_created_at = now - timedelta(minutes=5)

    async def fake_get_payload(_: str):
        return {"username": "admin3", "is_sudo": False, "created_at": token_created_at}

    async def fake_get_admin(_: str):
        return AdminAuthKVEntry(
            id=3,
            username="admin3",
            is_sudo=False,
            is_disabled=False,
            password_reset_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(authentication, "get_admin_payload", fake_get_payload)
    monkeypatch.setattr(authentication.admin_auth_cache_service, "get_admin", fake_get_admin)

    with pytest.raises(HTTPException) as exc_info:
        await authentication.get_current_nats_enabled(
            request=_build_request("GET"),
            db=AsyncMock(),
            token="token",
        )

    assert exc_info.value.status_code == 401
