from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from app.telegram.handlers.admin import main_menu
from app.telegram.utils.texts import Message as RealTexts


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
@pytest.mark.parametrize("error", [ValueError("Node is not connected"), RuntimeError("database is down")])
async def test_sync_users_goes_on_past_a_failed_node_and_names_it(
    monkeypatch, admin, fake_message, fake_callback, error
):
    monkeypatch.setattr(main_menu, "Texts", RealTexts)  # the real text names the nodes
    event = type(fake_callback)(message=type(fake_message)())
    names = ["n1", "n<2>", "n3"]
    db = SimpleNamespace(rollback=AsyncMock())
    nodes = SimpleNamespace(nodes=[SimpleNamespace(id=index, name=name) for index, name in enumerate(names, 1)])

    async def sync_node_users(db, node_id, flush_users):
        if node_id == 2:
            raise error

    sync = AsyncMock(side_effect=sync_node_users)
    monkeypatch.setattr(main_menu.node_operator, "get_db_nodes", AsyncMock(return_value=nodes))
    monkeypatch.setattr(main_menu.node_operator, "sync_node_users", sync)
    monkeypatch.setattr(main_menu, "_render_main_menu", AsyncMock(return_value=(None, "menu")))

    await main_menu.sync_users(event, db=db, admin=admin)

    assert [call.args[1] for call in sync.await_args_list] == [1, 2, 3]  # n3 still synced after n2 failed
    assert db.rollback.await_count == (0 if isinstance(error, ValueError) else 1)
    # Sent as a message: the callback was already answered and may have expired
    text = event.message.answer.await_args_list[-1].args[0]
    assert "n&lt;2&gt;" in text and "n1" not in text and "n3" not in text  # sent as HTML
    assert event.answer.await_count == 1
    assert main_menu.node_operator.get_db_nodes.await_args.args[1].enabled is True


@pytest.mark.asyncio
async def test_sync_users_survives_an_expired_callback(monkeypatch, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    event.answer = AsyncMock(side_effect=[None, TelegramBadRequest(method="m", message="query is too old")])
    nodes = SimpleNamespace(nodes=[SimpleNamespace(id=1, name="n1")])
    monkeypatch.setattr(main_menu.node_operator, "get_db_nodes", AsyncMock(return_value=nodes))
    monkeypatch.setattr(main_menu.node_operator, "sync_node_users", AsyncMock())
    monkeypatch.setattr(main_menu, "_render_main_menu", AsyncMock(return_value=(None, "menu")))

    await main_menu.sync_users(event, db=object(), admin=admin)

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
