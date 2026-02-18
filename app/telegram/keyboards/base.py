from enum import StrEnum
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

from app.telegram.utils.texts import Button as Texts


class CancelAction(StrEnum):
    cancel = "cancel"


class CancelKeyboard(InlineKeyboardBuilder):
    def __init__(self, action: CallbackData | CancelAction | str | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if action is None or action == CancelAction.cancel.value:
            action = self.Callback(action=CancelAction.cancel)
        elif isinstance(action, CancelAction):
            action = self.Callback(action=action)

        self.button(text=Texts.cancel, callback_data=action)
        self.adjust(1, 1)

    class Callback(CallbackData, prefix=""):
        action: CancelAction = CancelAction.cancel
