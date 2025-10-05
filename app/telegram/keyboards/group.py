from enum import StrEnum
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.models.group import GroupsResponse
from aiogram.filters.callback_data import CallbackData

from app.telegram.keyboards.base import CancelKeyboard, CancelAction
from app.telegram.keyboards.user import UserPanel
from app.telegram.utils.texts import Button as Texts


class SelectGroupAction(StrEnum):
    select = "select"
    create = "create"
    modify = "modify"


class GroupsSelector(InlineKeyboardBuilder):
    def __init__(self, groups: GroupsResponse, selected_groups: list[int] = None, user_id: int = 0, *args, **kwargs):
        selected_groups = selected_groups or []
        super().__init__(*args, **kwargs)
        for group in groups.groups:
            self.button(
                text=("✅" if group.id in selected_groups else "❌") + f" {group.name}",
                callback_data=self.Callback(group_id=group.id, user_id=user_id),
            )
        self.button(
            text=Texts.cancel,
            callback_data=UserPanel.Callback(user_id=user_id)
            if user_id
            else CancelKeyboard.Callback(action=CancelAction.cancel),
        )
        self.button(
            text=Texts.done,
            callback_data=self.Callback(action=SelectGroupAction.modify if user_id else SelectGroupAction.create),
        )
        self.adjust(*[1 for i in groups.groups], 2)

    class Callback(CallbackData, prefix="select_group"):
        action: SelectGroupAction = SelectGroupAction.select
        group_id: int = 0
        user_id: int = 0
