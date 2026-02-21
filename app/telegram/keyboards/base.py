from enum import StrEnum
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

from app.telegram.utils.texts import Button as Texts


class CancelAction(StrEnum):
    cancel = "cancel"


class CancelKeyboard(InlineKeyboardBuilder):
    def __init__(self, action: CallbackData = CancelAction.cancel, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.button(text=Texts.cancel, callback_data=action or self.Callback())
        self.adjust(1, 1)

    class Callback(CallbackData, prefix=""):
        action: CancelAction = CancelAction.cancel
