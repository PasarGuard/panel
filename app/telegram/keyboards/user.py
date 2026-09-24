from enum import Enum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import CopyTextButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.models.admin import AdminDetails
from app.models.user import UserResponse, UserStatus
from app.models.user_template import UserTemplate
from app.operation.permissions import PermissionDenied, enforce_permission
from app.telegram.utils.texts import Button as Texts

from .base import CancelAction, CancelKeyboard
from .confim_action import ConfirmAction


def _has_permission(admin: AdminDetails | None, resource: str, action: str) -> bool:
    """Return True if admin has the given permission."""
    if not admin:
        return False
    try:
        enforce_permission(admin, resource, action)
        return True
    except PermissionDenied:
        return False


class UserPanelAction(str, Enum):
    show = "show"
    disable = "disable"
    enable = "enable"
    delete = "delete"
    revoke_sub = "revoke_sub"
    reset_usage = "reset_usage"
    activate_next_plan = "activate_next_plan"
    modify_with_template = "modify_with_template"
    modify_data_limit = "modify_data_limit"
    modify_expiry = "modify_expiry"
    modify_note = "modify_note"
    modify_groups = "modify_groups"
    subscription_qr = "subscription_qr"
    v2ray_links = "v2ray_links"


class UserPanel(InlineKeyboardBuilder):
    class Callback(CallbackData, prefix="user"):
        user_id: int
        action: UserPanelAction = UserPanelAction.show

    def __init__(self, user: UserResponse, admin: AdminDetails | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        can_modify = _has_permission(admin, "users", "update")
        can_delete = _has_permission(admin, "users", "delete")
        can_revoke_sub = _has_permission(admin, "users", "revoke_sub")
        can_reset_usage = _has_permission(admin, "users", "reset_usage")
        can_activate_next_plan = _has_permission(admin, "users", "activate_next_plan")

        if can_modify:
            if user.status == UserStatus.active:
                self.button(
                    text=Texts.disable,
                    callback_data=ConfirmAction.Callback(
                        action=self.Callback(action=UserPanelAction.disable, user_id=user.id).pack(),
                        cancel=self.Callback(user_id=user.id).pack(),
                    ),
                )
            else:
                self.button(
                    text=Texts.enable,
                    callback_data=ConfirmAction.Callback(
                        action=self.Callback(action=UserPanelAction.enable, user_id=user.id).pack(),
                        cancel=self.Callback(user_id=user.id).pack(),
                    ),
                )
        if can_delete:
            self.button(
                text=Texts.delete,
                callback_data=ConfirmAction.Callback(
                    action=self.Callback(action=UserPanelAction.delete, user_id=user.id).pack(),
                    cancel=self.Callback(user_id=user.id).pack(),
                ),
            )
        if can_revoke_sub:
            self.button(
                text=Texts.revoke_sub,
                callback_data=ConfirmAction.Callback(
                    action=self.Callback(action=UserPanelAction.revoke_sub, user_id=user.id).pack(),
                    cancel=self.Callback(user_id=user.id).pack(),
                ),
            )
        if can_reset_usage:
            self.button(
                text=Texts.reset_usage,
                callback_data=ConfirmAction.Callback(
                    action=self.Callback(action=UserPanelAction.reset_usage, user_id=user.id).pack(),
                    cancel=self.Callback(user_id=user.id).pack(),
                ),
            )
        if can_modify:
            self.button(
                text=Texts.modify_data_limit,
                callback_data=self.Callback(action=UserPanelAction.modify_data_limit, user_id=user.id),
            )
            self.button(
                text=Texts.modify_expiry,
                callback_data=self.Callback(action=UserPanelAction.modify_expiry, user_id=user.id),
            )
            self.button(
                text=Texts.modify_note,
                callback_data=self.Callback(action=UserPanelAction.modify_note, user_id=user.id),
            )
            self.button(
                text=Texts.modify_groups,
                callback_data=self.Callback(action=UserPanelAction.modify_groups, user_id=user.id),
            )
        if can_activate_next_plan and not user.next_plan:
            self.button(
                text=Texts.activate_next_plan,
                callback_data=ConfirmAction.Callback(
                    action=self.Callback(action=UserPanelAction.activate_next_plan, user_id=user.id).pack(),
                    cancel=self.Callback(user_id=user.id).pack(),
                ),
            )
        if can_modify:
            self.button(
                text=Texts.modify_with_template,
                callback_data=self.Callback(action=UserPanelAction.modify_with_template, user_id=user.id),
            )

        self.button(text=Texts.subscription_url, copy_text=CopyTextButton(text=user.subscription_url))
        self.button(
            text=Texts.subscription_qr,
            callback_data=self.Callback(action=UserPanelAction.subscription_qr, user_id=user.id),
        )
        self.button(
            text=Texts.v2ray_links,
            callback_data=self.Callback(action=UserPanelAction.v2ray_links, user_id=user.id),
        )

        self.button(
            text=Texts.back,
            callback_data=CancelKeyboard.Callback(action=CancelAction.cancel),
        )

        self.adjust(2, 2, 2, 2, 1, 1, 1)


class ChooseStatus(InlineKeyboardBuilder):
    class Callback(CallbackData, prefix="user"):
        status: str

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.button(text=Texts.on_hold, callback_data=self.Callback(status=UserStatus.on_hold.value))
        self.button(text=Texts.enable, callback_data=self.Callback(status=UserStatus.active.value))
        self.adjust(2, repeat=True)


class ChooseTemplate(InlineKeyboardBuilder):
    class Callback(CallbackData, prefix="choose_template"):
        template_id: int
        user_id: int = 0  # in case choose template for modify

    def __init__(self, templates: list[UserTemplate], user_id: int = 0, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for template in templates:
            self.button(
                text=template.name,
                callback_data=self.Callback(template_id=template.id, user_id=user_id).pack(),
            )

        self.button(
            text=Texts.back,
            callback_data=UserPanel.Callback(user_id=user_id).pack()
            if user_id
            else CancelKeyboard.Callback(action=CancelAction.cancel).pack(),
        )
        self.adjust(1, repeat=True)


class RandomUsername(InlineKeyboardBuilder):
    class Callback(CallbackData, prefix="random_username"):
        with_template: bool = False

    def __init__(self, with_template: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.button(text=Texts.random_username, callback_data=self.Callback(with_template=with_template))
        self.button(
            text=Texts.back,
            callback_data=CancelKeyboard.Callback(action=CancelAction.cancel),
        )
        self.adjust(1, repeat=True)
