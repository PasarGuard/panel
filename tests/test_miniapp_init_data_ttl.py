from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import authentication


class _TelegramSettings:
    mini_app_login = True
    enable = True
    token = "123456:bot-token"


async def _telegram_settings() -> _TelegramSettings:
    return _TelegramSettings()


@pytest.mark.asyncio
async def test_miniapp_rejects_stale_init_data(monkeypatch):
    stale = SimpleNamespace(
        auth_date=datetime.now(UTC) - timedelta(days=30),
        user=SimpleNamespace(id=42),
    )
    monkeypatch.setattr(authentication, "telegram_settings", _telegram_settings)
    monkeypatch.setattr(authentication, "safe_parse_webapp_init_data", lambda **_: stale)

    with pytest.raises(HTTPException) as exc_info:
        await authentication.validate_mini_app_admin(None, "init-data")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_miniapp_accepts_fresh_init_data(monkeypatch):
    fresh = SimpleNamespace(
        auth_date=datetime.now(UTC),
        user=SimpleNamespace(id=42),
    )

    async def _find_admins_by_telegram_id(db, telegram_id, limit=2):
        return []

    async def _get_admin_by_telegram_id(db, telegram_id, load_users=True, load_usage_logs=True):
        return None

    monkeypatch.setattr(authentication, "telegram_settings", _telegram_settings)
    monkeypatch.setattr(authentication, "safe_parse_webapp_init_data", lambda **_: fresh)
    monkeypatch.setattr(authentication, "find_admins_by_telegram_id", _find_admins_by_telegram_id)
    monkeypatch.setattr(authentication, "get_admin_by_telegram_id", _get_admin_by_telegram_id)

    assert await authentication.validate_mini_app_admin(None, "init-data") is None
