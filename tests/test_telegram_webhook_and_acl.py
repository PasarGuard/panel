from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import system
from app.telegram.middlewares.acl import ACLMiddleware


def _patch_webhook_settings(monkeypatch, webhook_secret: str | None) -> None:
    async def _telegram_settings():
        return SimpleNamespace(enable=True, webhook_secret=webhook_secret)

    monkeypatch.setattr(system, "telegram_settings", _telegram_settings)
    # No bot: an accepted request returns 200 without parsing or dispatching the update.
    monkeypatch.setattr(system, "get_bot", lambda: None)


@pytest.mark.parametrize(("configured", "presented"), [("", ""), (None, ""), ("s3cret", "wrong"), ("s3cret", "")])
async def test_webhook_rejects_missing_or_wrong_secret(monkeypatch, configured, presented):
    _patch_webhook_settings(monkeypatch, configured)

    with pytest.raises(HTTPException) as exc_info:
        await system.webhook_handler(None, presented)

    assert exc_info.value.status_code == 403


async def test_webhook_accepts_the_configured_secret(monkeypatch):
    _patch_webhook_settings(monkeypatch, "s3cret")

    response = await system.webhook_handler(None, "s3cret")

    assert response.status_code == 200


def _update(**fields) -> SimpleNamespace:
    return SimpleNamespace(**{"message": None, "callback_query": None, "inline_query": None, **fields})


@pytest.mark.parametrize(
    "event",
    [
        _update(edited_message=SimpleNamespace(from_user=SimpleNamespace(id=1))),
        _update(message=SimpleNamespace(from_user=None)),
    ],
)
async def test_acl_skips_updates_without_a_sender(event):
    calls = []

    async def handler(event, data):
        calls.append(event)

    assert await ACLMiddleware()(handler, event, {}) is None
    assert calls == []
