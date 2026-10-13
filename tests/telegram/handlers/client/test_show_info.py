from unittest.mock import AsyncMock

import pytest

from app.telegram.handlers.client import show_info


class _TextValue(str):
    def __call__(self, *args, **kwargs):
        return str(self)


class _DummyTexts:
    def __getattr__(self, name):
        return _TextValue(name)


@pytest.fixture(autouse=True)
def patch_texts(monkeypatch):
    monkeypatch.setattr(show_info, "Texts", _DummyTexts())


@pytest.mark.asyncio
async def test_get_user_client_links_as_text(monkeypatch, fake_user, fake_message):
    event = type(fake_message)(text="/sub/token")

    monkeypatch.setattr(show_info.user_operations, "get_validated_sub", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(show_info.user_operations, "validate_user", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(show_info.subscription_operations, "validated_user", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(show_info.subscription_operations, "fetch_config", AsyncMock(return_value=("vmess://a", None)))

    await show_info.get_user(event, db=object())

    assert event.reply.await_count == 1
    assert event.answer.await_count == 1


@pytest.mark.asyncio
async def test_get_user_client_links_as_file(monkeypatch, fake_user, fake_message):
    event = type(fake_message)(text="/sub/token")

    monkeypatch.setattr(show_info.user_operations, "get_validated_sub", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(show_info.user_operations, "validate_user", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(show_info.subscription_operations, "validated_user", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(show_info.subscription_operations, "fetch_config", AsyncMock(return_value=("x" * 5000, None)))

    await show_info.get_user(event, db=object())

    event.answer_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_user_client_not_found(monkeypatch, fake_message):
    event = type(fake_message)(text="/sub/token")

    monkeypatch.setattr(show_info.user_operations, "get_validated_sub", AsyncMock(side_effect=ValueError("missing")))

    await show_info.get_user(event, db=object())

    event.reply.assert_awaited_once()
