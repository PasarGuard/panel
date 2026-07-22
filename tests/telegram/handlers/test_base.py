from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.telegram.handlers import base


class _TextValue(str):
    def __call__(self, *args, **kwargs):
        return str(self)


class _DummyTexts:
    def __getattr__(self, name):
        return _TextValue(name)


@pytest.fixture(autouse=True)
def patch_texts(monkeypatch, fake_message, fake_callback):
    monkeypatch.setattr(base, "Texts", _DummyTexts())
    monkeypatch.setattr(base.types, "Message", type(fake_message))
    monkeypatch.setattr(base.types, "CallbackQuery", type(fake_callback))
    monkeypatch.setattr(
        base,
        "telegram_settings",
        AsyncMock(return_value=type("S", (), {"mini_app_login": False, "mini_app_web_url": "https://panel"})()),
    )


@pytest.mark.asyncio
async def test_command_start_handler_for_admin_message(monkeypatch, admin, fake_state, fake_message):
    event = type(fake_message)(text="/start")
    fake_state._state = "busy"
    fake_state._data = {"messages_to_delete": [10]}

    monkeypatch.setattr(base, "delete_messages", AsyncMock())
    monkeypatch.setattr(base.system_operator, "get_system_stats", AsyncMock(return_value={"ok": True}))
    monkeypatch.setattr(
        base,
        "telegram_settings",
        AsyncMock(return_value=type("S", (), {"mini_app_login": True, "mini_app_web_url": "https://panel"})()),
    )

    await base.command_start_handler(event, admin, fake_state, db=object())

    base.delete_messages.assert_awaited_once()
    event.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_command_start_handler_callback_falls_back_to_answer(monkeypatch, admin, fake_message, fake_callback):
    message = type(fake_message)()
    message.edit_text = AsyncMock(side_effect=TelegramBadRequest(method="m", message="bad"))
    event = type(fake_callback)(message=message)

    monkeypatch.setattr(base.system_operator, "get_system_stats", AsyncMock(return_value={}))
    monkeypatch.setattr(
        base,
        "telegram_settings",
        AsyncMock(return_value=type("S", (), {"mini_app_login": False, "mini_app_web_url": "https://panel"})()),
    )

    await base.command_start_handler(event, admin, None, db=object())

    event.message.edit_text.assert_awaited_once()
    event.message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_command_start_handler_non_admin(fake_message):
    event = type(fake_message)(text="/start")

    await base.command_start_handler(event, None, None, db=None)

    event.answer.assert_awaited_once()
