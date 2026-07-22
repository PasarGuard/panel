from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db.models import UserStatus
from app.telegram.handlers.admin import user as user_h
from app.telegram.keyboards.group import GroupsSelector, SelectGroupAction
from app.telegram.keyboards.user import ChooseStatus, ChooseTemplate, UserPanel, UserPanelAction


class _TextValue(str):
    def __call__(self, *args, **kwargs):
        return str(self)


class _DummyTexts:
    def __getattr__(self, name):
        return _TextValue(name)


@pytest.fixture(autouse=True)
def patch_event_types(monkeypatch, fake_message, fake_callback, fake_inline_query):
    monkeypatch.setattr(user_h, "Texts", _DummyTexts())
    monkeypatch.setattr(user_h, "Message", type(fake_message))
    monkeypatch.setattr(user_h, "CallbackQuery", type(fake_callback))
    monkeypatch.setattr(user_h, "InlineQuery", type(fake_inline_query))
    monkeypatch.setattr(user_h, "delete_messages", AsyncMock())
    monkeypatch.setattr(user_h, "add_to_messages_to_delete", AsyncMock())


@pytest.fixture
def groups_response():
    return SimpleNamespace(groups=[SimpleNamespace(id=1, name="g1"), SimpleNamespace(id=2, name="g2")])


@pytest.mark.asyncio
async def test_create_user(fake_state, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())

    await user_h.create_user(event, fake_state)

    assert await fake_state.get_state() == user_h.forms.CreateUser.username
    event.message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_username_message_happy(monkeypatch, fake_state, admin, fake_message):
    event = type(fake_message)(text="alice")
    monkeypatch.setattr(user_h, "delete_messages", AsyncMock())
    monkeypatch.setattr(user_h, "add_to_messages_to_delete", AsyncMock())
    monkeypatch.setattr(user_h.UserValidator, "validate_username", lambda x: x)
    monkeypatch.setattr(user_h.user_operations, "get_validated_user", AsyncMock(side_effect=ValueError("not found")))

    await user_h.process_username(event, fake_state, db=object(), admin=admin)

    assert await fake_state.get_state() == user_h.forms.CreateUser.data_limit
    event.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_username_callback_duplicate(monkeypatch, fake_state, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    monkeypatch.setattr(user_h, "delete_messages", AsyncMock())
    monkeypatch.setattr(user_h, "add_to_messages_to_delete", AsyncMock())
    monkeypatch.setattr(user_h.random, "choices", lambda *args, **kwargs: list("ABCDE"))
    monkeypatch.setattr(user_h.user_operations, "get_validated_user", AsyncMock(return_value=SimpleNamespace()))

    await user_h.process_username(event, fake_state, db=object(), admin=admin)

    event.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_data_limit_validation(fake_state, fake_message):
    event = type(fake_message)(text="-1")

    await user_h.process_data_limit(event, fake_state)

    event.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_expire_zero(monkeypatch, fake_state, admin, groups_response, fake_message):
    event = type(fake_message)(text="0")
    monkeypatch.setattr(user_h, "delete_messages", AsyncMock())
    monkeypatch.setattr(user_h, "add_to_messages_to_delete", AsyncMock())
    monkeypatch.setattr(user_h.group_operations, "get_all_groups", AsyncMock(return_value=groups_response))

    await user_h.process_expire(event, fake_state, db=object(), admin=admin)

    assert await fake_state.get_state() == user_h.forms.CreateUser.group_ids


@pytest.mark.asyncio
async def test_process_status_on_hold(monkeypatch, fake_state, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = ChooseStatus.Callback(status=UserStatus.on_hold.value)
    monkeypatch.setattr(user_h, "delete_messages", AsyncMock())
    monkeypatch.setattr(user_h, "add_to_messages_to_delete", AsyncMock())

    await user_h.process_status(event, db=object(), state=fake_state, callback_data=callback_data, admin=admin)

    assert await fake_state.get_state() == user_h.forms.CreateUser.on_hold_timeout


@pytest.mark.asyncio
async def test_process_on_hold_timeout_invalid(fake_state, admin, fake_message):
    event = type(fake_message)(text="bad")

    await user_h.process_on_hold_timeout(event, fake_state, db=object(), admin=admin)

    event.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_select_groups_toggles(monkeypatch, fake_state, admin, groups_response, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = GroupsSelector.Callback(action=SelectGroupAction.select, group_id=1, user_id=0)
    monkeypatch.setattr(user_h.group_operations, "get_all_groups", AsyncMock(return_value=groups_response))

    await user_h.select_groups(event, db=object(), state=fake_state, callback_data=callback_data, admin=admin)
    await user_h.select_groups(event, db=object(), state=fake_state, callback_data=callback_data, admin=admin)

    assert await fake_state.get_value("group_ids") == []


@pytest.mark.asyncio
async def test_process_done_without_groups(fake_state, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())

    await user_h.process_done(event, db=object(), admin=admin, state=fake_state)

    event.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_done_creates_user(monkeypatch, fake_state, admin, fake_user, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    fake_state._data = {
        "username": "alice",
        "data_limit": 1.5,
        "duration": 3,
        "status": UserStatus.active.value,
        "group_ids": [1],
        "messages_to_delete": [1],
    }
    monkeypatch.setattr(user_h, "delete_messages", AsyncMock())
    monkeypatch.setattr(user_h.user_operations, "create_user", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.user_operations, "validate_all_groups", AsyncMock(return_value=[]))

    await user_h.process_done(event, db=object(), admin=admin, state=fake_state)

    user_h.user_operations.create_user.assert_awaited_once()
    event.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_modify_groups_user_not_found(monkeypatch, fake_state, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = UserPanel.Callback(user_id=1, action=UserPanelAction.modify_groups)
    monkeypatch.setattr(user_h.user_operations, "get_user_by_id", AsyncMock(side_effect=ValueError("missing")))

    await user_h.modify_groups(event, db=object(), state=fake_state, callback_data=callback_data, admin=admin)

    event.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_modify_groups_done_no_groups(fake_state, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())

    await user_h.modify_groups_done(event, db=object(), admin=admin, state=fake_state)

    event.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_modify_expiry_sets_state(fake_state, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = UserPanel.Callback(user_id=1, action=UserPanelAction.modify_expiry)

    await user_h.modify_expiry(event, callback_data=callback_data, state=fake_state)

    assert await fake_state.get_state() == user_h.forms.ModifyUser.new_expiry


@pytest.mark.asyncio
async def test_modify_expiry_done_invalid(fake_state, admin, fake_message):
    event = type(fake_message)(text="bad")

    await user_h.modify_expiry_done(event, state=fake_state, db=object(), admin=admin)

    event.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_modify_data_limit_sets_state(fake_state, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = UserPanel.Callback(user_id=1, action=UserPanelAction.modify_data_limit)

    await user_h.modify_data_limit(event, callback_data=callback_data, state=fake_state)

    assert await fake_state.get_state() == user_h.forms.ModifyUser.new_data_limit


@pytest.mark.asyncio
async def test_modify_data_limit_done_invalid(fake_state, admin, fake_message):
    event = type(fake_message)(text="abc")

    await user_h.modify_data_limit_done(event, state=fake_state, db=object(), admin=admin)

    event.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_modify_note_sets_state(fake_state, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = UserPanel.Callback(user_id=1, action=UserPanelAction.modify_note)

    await user_h.modify_note(event, callback_data=callback_data, state=fake_state)

    assert await fake_state.get_state() == user_h.forms.ModifyUser.new_note


@pytest.mark.asyncio
async def test_modify_note_done_user_not_found(monkeypatch, fake_state, admin, fake_message):
    event = type(fake_message)(text="note")
    fake_state._data = {"user_id": 10}
    monkeypatch.setattr(user_h, "delete_messages", AsyncMock())
    monkeypatch.setattr(user_h, "add_to_messages_to_delete", AsyncMock())
    monkeypatch.setattr(user_h.user_operations, "get_user_by_id", AsyncMock(side_effect=ValueError("missing")))

    await user_h.modify_note_done(event, state=fake_state, db=object(), admin=admin)

    event.answer.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "func_name,action",
    [
        ("disable_user", UserPanelAction.disable),
        ("enable_user", UserPanelAction.enable),
        ("delete_user", UserPanelAction.delete),
        ("revoke_sub", UserPanelAction.revoke_sub),
        ("reset_usage", UserPanelAction.reset_usage),
        ("activate_next_plan", UserPanelAction.activate_next_plan),
    ],
)
async def test_direct_user_actions(monkeypatch, admin, fake_user, func_name, action, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = UserPanel.Callback(user_id=11, action=action)

    monkeypatch.setattr(user_h.user_operations, "get_user_by_id", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.user_operations, "validate_all_groups", AsyncMock(return_value=[]))
    monkeypatch.setattr(user_h.user_operations, "modify_user", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.user_operations, "remove_user", AsyncMock())
    monkeypatch.setattr(user_h.user_operations, "revoke_user_sub", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.user_operations, "reset_user_data_usage", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.user_operations, "active_next_plan", AsyncMock(return_value=fake_user))

    await getattr(user_h, func_name)(event, admin=admin, db=object(), callback_data=callback_data)

    assert event.answer.await_count >= 1


@pytest.mark.asyncio
async def test_modify_with_template_no_templates(monkeypatch, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = UserPanel.Callback(user_id=11, action=UserPanelAction.modify_with_template)
    monkeypatch.setattr(user_h.user_templates, "get_user_templates", AsyncMock(return_value=[]))

    await user_h.modify_with_template(event, db=object(), admin=admin, callback_data=callback_data)

    event.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_modify_with_template_done(monkeypatch, admin, fake_user, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = ChooseTemplate.Callback(template_id=1, user_id=11)
    monkeypatch.setattr(user_h.user_operations, "get_user_by_id", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.user_operations, "modify_user_with_template", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.user_operations, "validate_all_groups", AsyncMock(return_value=[]))

    await user_h.modify_with_template_done(event, db=object(), admin=admin, callback_data=callback_data)

    event.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_user_from_template_no_templates(monkeypatch, admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    monkeypatch.setattr(user_h.user_templates, "get_user_templates", AsyncMock(return_value=[]))

    await user_h.create_user_from_template(event, db=object(), admin=admin)

    event.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_user_from_template_username(fake_state, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = ChooseTemplate.Callback(template_id=1)

    await user_h.create_user_from_template_username(event, state=fake_state, callback_data=callback_data)

    assert await fake_state.get_state() == user_h.forms.CreateUserFromTemplate.username


@pytest.mark.asyncio
async def test_create_user_from_template_choose(monkeypatch, fake_state, admin, fake_user, fake_message):
    event = type(fake_message)(text="alice")
    fake_state._data = {"template_id": 1, "messages_to_delete": []}
    template = SimpleNamespace(username_prefix="", username_suffix="")

    monkeypatch.setattr(user_h, "delete_messages", AsyncMock())
    monkeypatch.setattr(user_h, "add_to_messages_to_delete", AsyncMock())
    monkeypatch.setattr(user_h.UserValidator, "validate_username", lambda x: x)
    monkeypatch.setattr(user_h.user_templates, "get_validated_user_template", AsyncMock(return_value=template))
    monkeypatch.setattr(user_h.user_operations, "get_validated_user", AsyncMock(side_effect=ValueError("missing")))
    monkeypatch.setattr(user_h.user_operations, "create_user_from_template", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.user_operations, "validate_all_groups", AsyncMock(return_value=[]))

    await user_h.create_user_from_template_choose(event, state=fake_state, db=object(), admin=admin)

    user_h.user_operations.create_user_from_template.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_user_by_sub_unauthorized(monkeypatch, regular_admin, fake_user, fake_message):
    event = type(fake_message)(text="/sub/abc")
    fake_user.admin = SimpleNamespace(username="other")

    monkeypatch.setattr(user_h.user_operations, "get_validated_sub", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.user_operations, "validate_user", AsyncMock(return_value=fake_user))

    await user_h.get_user_by_sub(event, db=object(), admin=regular_admin)

    event.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_v2ray_links_unavailable(monkeypatch, admin, fake_user, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = UserPanel.Callback(user_id=11, action=UserPanelAction.v2ray_links)
    monkeypatch.setattr(user_h.user_operations, "get_validated_user_by_id", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.user_operations, "validate_user", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.subscription_operations, "validated_user", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.subscription_operations, "fetch_config", AsyncMock(return_value=("", None)))

    await user_h.get_v2ray_links(event, db=object(), admin=admin, callback_data=callback_data)

    event.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_user_message_not_found(monkeypatch, admin, fake_message):
    event = type(fake_message)(text="missing")
    monkeypatch.setattr(user_h.user_operations, "get_user", AsyncMock(side_effect=ValueError("missing")))

    await user_h.get_user(event, admin=admin, db=object())

    event.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_user_callback_happy(monkeypatch, admin, fake_user, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback_data = UserPanel.Callback(user_id=11, action=UserPanelAction.show)
    monkeypatch.setattr(user_h.user_operations, "get_user_by_id", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(user_h.user_operations, "validate_all_groups", AsyncMock(return_value=[]))

    await user_h.get_user(event, admin=admin, db=object(), callback_data=callback_data)

    event.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_user_and_debug(monkeypatch, admin, fake_user, fake_inline_query, fake_message, fake_callback):
    inline = type(fake_inline_query)(query="al")
    callback = type(fake_callback)(message=type(fake_message)(), data="any:payload")

    monkeypatch.setattr(user_h.user_operations, "get_users", AsyncMock(return_value=SimpleNamespace(users=[fake_user])))

    await user_h.search_user(inline, admin=admin, db=object())
    await user_h.debug(callback)

    inline.answer.assert_awaited_once()
    callback.answer.assert_awaited_once_with("any:payload", show_alert=True)
