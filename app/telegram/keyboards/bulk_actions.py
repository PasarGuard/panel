from enum import Enum

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData

from app.models.user import UsernameGenerationStrategy
from app.telegram.keyboards.admin import AdminPanel, AdminPanelAction
from app.telegram.keyboards.base import CancelKeyboard, CancelAction
from app.telegram.utils.texts import Button as Texts


class BulkAction(str, Enum):
    delete_expired = "delete_expired"
    modify_expiry = "modify_expiry"
    modify_data_limit = "modify_data_limit"
    create_from_template = "create_from_template"


class BulkActionPanel(InlineKeyboardBuilder):
    class Callback(CallbackData, prefix="bulk"):
        action: BulkAction
        amount: str = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.button(text=Texts.delete_expired, callback_data=self.Callback(action=BulkAction.delete_expired))
        self.button(text=Texts.modify_expiry, callback_data=self.Callback(action=BulkAction.modify_expiry))
        self.button(text=Texts.modify_data_limit, callback_data=self.Callback(action=BulkAction.modify_data_limit))
        self.button(
            text=Texts.bulk_create_from_template,
            callback_data=self.Callback(action=BulkAction.create_from_template),
        )

        self.button(
            text=Texts.back,
            callback_data=CancelKeyboard.Callback(action=CancelAction.cancel),
        )

        self.adjust(1, repeat=True)


class BulkTemplateSelector(InlineKeyboardBuilder):
    class Callback(CallbackData, prefix="bulk_template"):
        template_id: int

    def __init__(self, templates, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for template in templates:
            self.button(text=template.name, callback_data=self.Callback(template_id=template.id))

        self.button(
            text=Texts.back,
            callback_data=AdminPanel.Callback(action=AdminPanelAction.bulk_actions),
        )
        self.adjust(1, repeat=True)


class UsernameStrategySelector(InlineKeyboardBuilder):
    class Callback(CallbackData, prefix="bulk_strategy"):
        strategy: UsernameGenerationStrategy

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.button(text=Texts.random_strategy, callback_data=self.Callback(strategy=UsernameGenerationStrategy.random))
        self.button(
            text=Texts.sequence_strategy, callback_data=self.Callback(strategy=UsernameGenerationStrategy.sequence)
        )
        self.button(
            text=Texts.back,
            callback_data=AdminPanel.Callback(action=AdminPanelAction.bulk_actions),
        )
        self.adjust(1, 1)
