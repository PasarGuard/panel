from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.telegram.handlers.admin import main_menu


class _TextValue(str):
    def __call__(self, *args, **kwargs):
        return str(self)


class _DummyTexts:
    def __getattr__(self, name):
        return _TextValue(name)


@pytest.fixture(autouse=True)
def patch_texts(monkeypatch):
    monkeypatch.setattr(main_menu, "Texts", _DummyTexts())


@pytest.mark.asyncio
async def test_reload_data(monkeypatch, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    monkeypatch.setattr(main_menu.system_operator, "get_system_stats", AsyncMock(return_value={}))
    monkeypatch.setattr(
        main_menu,
        "telegram_settings",
        AsyncMock(return_value=SimpleNamespace(mini_app_login=True, mini_app_web_url="https://panel")),
    )

    await main_menu.reload_data(event, db=object(), admin=admin)

    event.message.edit_text.assert_awaited_once()
    event.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_reload_data_ignores_edit_error(monkeypatch, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    event.message.edit_text = AsyncMock(side_effect=TelegramBadRequest(method="m", message="bad"))
    monkeypatch.setattr(main_menu.system_operator, "get_system_stats", AsyncMock(return_value={}))
    monkeypatch.setattr(
        main_menu,
        "telegram_settings",
        AsyncMock(return_value=SimpleNamespace(mini_app_login=False, mini_app_web_url="https://panel")),
    )

    await main_menu.reload_data(event, db=object(), admin=admin)

    event.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_users(monkeypatch, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    nodes = SimpleNamespace(nodes=[SimpleNamespace(id=1), SimpleNamespace(id=2)])

    monkeypatch.setattr(main_menu.node_operator, "get_db_nodes", AsyncMock(return_value=nodes))
    monkeypatch.setattr(main_menu.node_operator, "sync_node_users", AsyncMock())
    monkeypatch.setattr(main_menu.system_operator, "get_system_stats", AsyncMock(return_value={}))
    monkeypatch.setattr(
        main_menu,
        "telegram_settings",
        AsyncMock(return_value=SimpleNamespace(mini_app_login=False, mini_app_web_url="https://panel")),
    )

    await main_menu.sync_users(event, db=object(), admin=admin)

    assert main_menu.node_operator.sync_node_users.await_count == 2
    assert event.answer.await_count == 2


@pytest.mark.asyncio
async def test_reconnect_all_nodes(monkeypatch, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())

    monkeypatch.setattr(main_menu.node_operator, "restart_all_node", AsyncMock())
    monkeypatch.setattr(main_menu.system_operator, "get_system_stats", AsyncMock(return_value={}))
    monkeypatch.setattr(
        main_menu,
        "telegram_settings",
        AsyncMock(return_value=SimpleNamespace(mini_app_login=False, mini_app_web_url="https://panel")),
    )

    await main_menu.reconnect_all_nodes(event, db=object(), admin=admin)

    main_menu.node_operator.restart_all_node.assert_awaited_once()
    assert event.answer.await_count == 2
