from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.notification import client as notification_client


@pytest.fixture
def old_session(monkeypatch):
    session = MagicMock(closed=False)
    session.close = AsyncMock()
    monkeypatch.setattr(notification_client, "client", session)
    return session


@pytest.mark.asyncio
async def test_settings_failure_does_not_close_working_session(monkeypatch, old_session):
    monkeypatch.setattr(notification_client, "notification_settings", AsyncMock(side_effect=RuntimeError("DB down")))
    with pytest.raises(RuntimeError, match="DB down"):
        await notification_client.define_client()
    assert notification_client.client is old_session
    old_session.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_replacement_failure_does_not_close_working_session(monkeypatch, old_session):
    monkeypatch.setattr(
        notification_client, "notification_settings", AsyncMock(return_value=SimpleNamespace(proxy_url=""))
    )
    monkeypatch.setattr(notification_client, "create_outbound_http_session", MagicMock(side_effect=ValueError("proxy")))
    with pytest.raises(ValueError, match="proxy"):
        await notification_client.define_client()
    assert notification_client.client is old_session
    old_session.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_replacement_awaits_old_session_close(monkeypatch, old_session):
    replacement = MagicMock()
    monkeypatch.setattr(
        notification_client, "notification_settings", AsyncMock(return_value=SimpleNamespace(proxy_url=""))
    )
    monkeypatch.setattr(notification_client, "create_outbound_http_session", MagicMock(return_value=replacement))
    await notification_client.define_client()
    assert notification_client.client is replacement
    old_session.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_close_is_idempotent_and_clears_global_reference(old_session):
    await notification_client.close_notification_client()
    await notification_client.close_notification_client()
    assert notification_client.client is None
    old_session.close.assert_awaited_once_with()
