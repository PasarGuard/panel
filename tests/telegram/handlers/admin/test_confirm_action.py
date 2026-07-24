from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.telegram.handlers.admin import confirm_action
from app.telegram.keyboards.user import UserPanel, UserPanelAction


class _TextValue(str):
    def __call__(self, *args, **kwargs):
        return str(self)


class _DummyTexts:
    def __getattr__(self, name):
        return _TextValue(name)


@pytest.fixture(autouse=True)
def patch_texts(monkeypatch):
    monkeypatch.setattr(confirm_action, "Texts", _DummyTexts())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    [
        UserPanelAction.disable,
        UserPanelAction.enable,
        UserPanelAction.delete,
        UserPanelAction.revoke_sub,
        UserPanelAction.reset_usage,
        UserPanelAction.activate_next_plan,
    ],
)
async def test_confirm_action_for_user_actions(monkeypatch, admin, action, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    user = SimpleNamespace(username="alice")
    callback = SimpleNamespace(
        action=UserPanel.Callback(user_id=11, action=action).pack(),
        cancel=UserPanel.Callback(user_id=11).pack(),
    )

    monkeypatch.setattr(confirm_action.user_operations, "get_user_by_id", AsyncMock(return_value=user))

    await confirm_action.confirm_action(event, callback, db=object(), admin=admin)

    confirm_action.user_operations.get_user_by_id.assert_awaited_once()
    event.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_confirm_action_default_text_without_user_action(admin, fake_message, fake_callback):
    event = type(fake_callback)(message=type(fake_message)())
    callback = SimpleNamespace(action="other:payload", cancel="cancel")

    await confirm_action.confirm_action(event, callback, db=object(), admin=admin)

    event.message.edit_text.assert_awaited_once()
