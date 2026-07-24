from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.user import UsernameGenerationStrategy
from app.telegram.handlers.admin import bulk_actions as bulk_h
from app.telegram.keyboards.bulk_actions import (
    BulkAction,
    BulkActionPanel,
    BulkTemplateSelector,
    UsernameStrategySelector,
)


class _TextValue(str):
    def __call__(self, *args, **kwargs):
        return str(self)


class _DummyTexts:
    def __getattr__(self, name):
        return _TextValue(name)


@pytest.fixture(autouse=True)
def patch_event_types(monkeypatch, fake_message, fake_callback):
    monkeypatch.setattr(bulk_h, "Texts", _DummyTexts())
    monkeypatch.setattr(bulk_h, "Message", type(fake_message))
    monkeypatch.setattr(bulk_h, "CallbackQuery", type(fake_callback))
    monkeypatch.setattr(bulk_h, "delete_messages", AsyncMock())
    monkeypatch.setattr(bulk_h, "add_to_messages_to_delete", AsyncMock())


@pytest.mark.asyncio
async def test_helpers_message_target_and_chunking(fake_message, fake_callback):
    msg = type(fake_message)()
    callback = type(fake_callback)(message=msg)

    assert bulk_h._message_target(msg) is msg
    assert bulk_h._message_target(callback) is msg
    chunks = bulk_h._chunk_subscription_urls(["a" * 3000, "b" * 3000], limit=3800)
    assert len(chunks) == 2


@pytest.mark.asyncio
async def test_bulk_actions_menu(admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())

    await bulk_h.bulk_actions(event, admin=admin)

    event.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_create_from_template_no_templates(monkeypatch, fake_state, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    monkeypatch.setattr(bulk_h.user_templates, "get_user_templates", AsyncMock(return_value=[]))

    await bulk_h.bulk_create_from_template(event, db=object(), state=fake_state, admin=admin)

    event.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_template_chosen(fake_state, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = BulkTemplateSelector.Callback(template_id=1)

    await bulk_h.bulk_template_chosen(event, state=fake_state, callback_data=callback_data)

    assert await fake_state.get_state() == bulk_h.forms.BulkCreateFromTemplate.count


@pytest.mark.asyncio
async def test_bulk_template_count_invalid(fake_state, fake_message):
    event = type(fake_message)(text="x")

    await bulk_h.bulk_template_count(event, state=fake_state)

    event.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_template_strategy_random(monkeypatch, fake_state, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = UsernameStrategySelector.Callback(strategy=UsernameGenerationStrategy.random)
    fake_state._data = {"template_id": 1, "count": 2}
    monkeypatch.setattr(bulk_h, "delete_messages", AsyncMock())
    monkeypatch.setattr(bulk_h, "_perform_bulk_creation", AsyncMock())

    await bulk_h.bulk_template_strategy(event, db=object(), state=fake_state, admin=admin, callback_data=callback_data)

    bulk_h._perform_bulk_creation.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_template_sequence_username_invalid(fake_state, admin, fake_message):
    event = type(fake_message)(text="bad name")

    await bulk_h.bulk_template_sequence_username(event, db=object(), state=fake_state, admin=admin)

    event.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_template_start_number_invalid(fake_state, admin, fake_message):
    event = type(fake_message)(text="-2")

    await bulk_h.bulk_template_start_number(event, db=object(), state=fake_state, admin=admin)

    event.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_perform_bulk_creation_success(monkeypatch, fake_state, admin, fake_message):
    event = type(fake_message)(text="run")
    monkeypatch.setattr(bulk_h, "delete_messages", AsyncMock())
    monkeypatch.setattr(
        bulk_h.user_operations,
        "bulk_create_users_from_template",
        AsyncMock(return_value=SimpleNamespace(created=2, subscription_urls=["https://a", "https://b"])),
    )

    await bulk_h._perform_bulk_creation(
        event,
        db=object(),
        admin=admin,
        state=fake_state,
        template_id=1,
        count=2,
        strategy=UsernameGenerationStrategy.random,
    )

    assert event.answer.await_count >= 2


@pytest.mark.asyncio
async def test_delete_expired_sets_state(fake_state, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())

    await bulk_h.delete_expired(event, state=fake_state)

    assert await fake_state.get_state() == bulk_h.forms.DeleteExpired.expired_before


@pytest.mark.asyncio
async def test_process_expire_before_validation(fake_state, fake_message):
    event = type(fake_message)(text="abc")

    await bulk_h.process_expire_before(event, state=fake_state)

    event.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_expired_done(monkeypatch, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = BulkActionPanel.Callback(action=BulkAction.delete_expired, amount="3")
    monkeypatch.setattr(
        bulk_h.user_operations,
        "delete_expired_users",
        AsyncMock(return_value=SimpleNamespace(count=5)),
    )

    await bulk_h.delete_expired_done(event, db=object(), admin=admin, callback_data=callback_data)

    event.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_modify_expiry_sets_state(fake_state, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())

    await bulk_h.modify_expiry(event, state=fake_state)

    assert await fake_state.get_state() == bulk_h.forms.BulkModify.expiry


@pytest.mark.asyncio
async def test_process_expiry_invalid(fake_state, fake_message):
    event = type(fake_message)(text="bad")

    await bulk_h.process_expiry(event, state=fake_state)

    event.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_modify_expiry_done(monkeypatch, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = BulkActionPanel.Callback(action=BulkAction.modify_expiry, amount="5")
    monkeypatch.setattr(bulk_h.user_operations, "bulk_modify_expire", AsyncMock(return_value=7))

    await bulk_h.modify_expiry_done(event, db=object(), admin=admin, callback_data=callback_data)

    event.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_modify_data_limit_sets_state(fake_state, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())

    await bulk_h.modify_data_limit(event, state=fake_state)

    assert await fake_state.get_state() == bulk_h.forms.BulkModify.data_limit


@pytest.mark.asyncio
async def test_process_data_limit_invalid(fake_state, fake_message):
    event = type(fake_message)(text="bad")

    await bulk_h.process_data_limit(event, state=fake_state)

    event.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_modify_data_limit_done(monkeypatch, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = BulkActionPanel.Callback(action=BulkAction.modify_data_limit, amount="4")
    monkeypatch.setattr(bulk_h.user_operations, "bulk_modify_datalimit", AsyncMock(return_value=9))

    await bulk_h.modify_data_limit_done(event, db=object(), admin=admin, callback_data=callback_data)

    event.message.edit_text.assert_awaited_once()
