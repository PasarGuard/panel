import asyncio
import json
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from fastapi import HTTPException

from app.models.admin import AdminStatus
from app.notification.discord import admin as discord_admin
from app.notification.telegram import admin as telegram_admin
from app.routers import admin as admin_router

SUBMITTED_PASSWORD = "correct-horse-battery-staple"


@pytest.mark.parametrize(
    ("db_admin", "expected_status"),
    [
        (None, 401),
        (SimpleNamespace(id=7, username="disabled-admin", status=AdminStatus.disabled), 403),
    ],
)
@pytest.mark.asyncio
async def test_failed_login_report_never_receives_submitted_password(
    monkeypatch: pytest.MonkeyPatch, db_admin: SimpleNamespace | None, expected_status: int
):
    validate_admin = AsyncMock(return_value=db_admin)
    report_login = AsyncMock()
    monkeypatch.setattr(admin_router, "validate_admin", validate_admin)
    monkeypatch.setattr(admin_router.notification, "admin_login", report_login)
    monkeypatch.setattr(admin_router, "get_client_ip", lambda request: "203.0.113.10")

    form_data = SimpleNamespace(username="disabled-admin", password=SUBMITTED_PASSWORD)
    with pytest.raises(HTTPException) as exc_info:
        await admin_router.admin_token(SimpleNamespace(), form_data, SimpleNamespace())
    await asyncio.sleep(0)

    assert exc_info.value.status_code == expected_status
    validate_admin.assert_awaited_once_with(ANY, "disabled-admin", SUBMITTED_PASSWORD)
    report_login.assert_awaited_once_with("disabled-admin", "203.0.113.10", False)
    assert SUBMITTED_PASSWORD not in repr(report_login.await_args)


@pytest.mark.asyncio
async def test_db_admin_login_uses_submitted_password_but_reports_only_safe_metadata(monkeypatch: pytest.MonkeyPatch):
    db_admin = SimpleNamespace(id=7, username="db-admin", status=AdminStatus.active)
    validate_admin = AsyncMock(return_value=db_admin)
    report_login = AsyncMock()
    create_admin_token = AsyncMock(return_value="access-token")
    monkeypatch.setattr(admin_router, "validate_admin", validate_admin)
    monkeypatch.setattr(admin_router.notification, "admin_login", report_login)
    monkeypatch.setattr(admin_router, "create_admin_token", create_admin_token)
    monkeypatch.setattr(admin_router, "get_client_ip", lambda request: "203.0.113.10")

    form_data = SimpleNamespace(username="db-admin", password=SUBMITTED_PASSWORD)
    token = await admin_router.admin_token(SimpleNamespace(), form_data, SimpleNamespace())
    await asyncio.sleep(0)

    assert token.access_token == "access-token"
    validate_admin.assert_awaited_once_with(ANY, "db-admin", SUBMITTED_PASSWORD)
    report_login.assert_awaited_once_with("db-admin", "203.0.113.10", True)
    assert SUBMITTED_PASSWORD not in repr(report_login.await_args)


@pytest.mark.asyncio
async def test_login_renderers_emit_safe_metadata_only(monkeypatch: pytest.MonkeyPatch):
    telegram_send = AsyncMock()
    discord_send = AsyncMock()
    settings = SimpleNamespace(notify_telegram=True, notify_discord=True)

    monkeypatch.setattr(telegram_admin, "notification_settings", AsyncMock(return_value=settings))
    monkeypatch.setattr(telegram_admin, "get_telegram_channel", lambda settings, entity: (123, None))
    monkeypatch.setattr(telegram_admin, "send_telegram_message", telegram_send)
    monkeypatch.setattr(discord_admin, "notification_settings", AsyncMock(return_value=settings))
    monkeypatch.setattr(discord_admin, "get_discord_webhook", lambda settings, entity: "https://example.test/hook")
    monkeypatch.setattr(discord_admin, "send_discord_webhook", discord_send)

    await telegram_admin.admin_login("db-admin", "203.0.113.10", False)
    await discord_admin.admin_login("db-admin", "203.0.113.10", False)

    telegram_payload = telegram_send.await_args.args[0]
    discord_payload = json.dumps(discord_send.await_args.args[0])
    for payload in (telegram_payload, discord_payload):
        assert "db-admin" in payload
        assert "203.0.113.10" in payload
        assert "password" not in payload.lower()
        assert SUBMITTED_PASSWORD not in payload
