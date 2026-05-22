from enum import Enum

from aiogram.utils.keyboard import InlineKeyboardBuilder, WebAppInfo
from aiogram.filters.callback_data import CallbackData

from app.models.admin import AdminDetails
from app.operation.permissions import enforce_permission, is_scope_all, PermissionDenied
from app.telegram.utils.texts import Button as Texts


class AdminPanelAction(str, Enum):
    sync_users = "sync_users"
    reconnect_all_nodes = "reconnect_all_nodes"
    refresh = "refresh"
    create_user = "create_user"
    create_user_from_template = "create_user_from_template"
    bulk_actions = "bulk_actions"


def _has_permission(admin: AdminDetails | None, resource: str, action: str) -> bool:
    """Return True if admin has the given permission."""
    if not admin:
        return False
    try:
        enforce_permission(admin, resource, action)
        return True
    except PermissionDenied:
        return False


class AdminPanel(InlineKeyboardBuilder):
    class Callback(CallbackData, prefix="panel"):
        action: AdminPanelAction

    def __init__(self, admin: AdminDetails | None = None, panel_url: str = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        adjust = []

        if panel_url and panel_url.startswith("https://"):
            self.button(text=Texts.open_panel, web_app=WebAppInfo(url=panel_url))
            adjust.append(1)

        self.button(text=Texts.refresh_data, callback_data=self.Callback(action=AdminPanelAction.refresh))

        can_read_nodes = _has_permission(admin, "nodes", "reconnect")
        can_read_users = _has_permission(admin, "users", "read")
        can_create_users = _has_permission(admin, "users", "create")
        # bulk_actions requires scope=all on users.update
        can_bulk = is_scope_all(admin, "users", "update") if admin else False

        if can_read_nodes:
            self.button(text=Texts.sync_users, callback_data=self.Callback(action=AdminPanelAction.sync_users))
            self.button(
                text=Texts.reconnect_all_nodes,
                callback_data=self.Callback(action=AdminPanelAction.reconnect_all_nodes),
            )
            adjust = adjust + [1, 2]

        if can_read_users:
            self.button(text=Texts.users, switch_inline_query_current_chat="")
            adjust.append(1)

        if can_bulk:
            self.button(text=Texts.bulk_actions, callback_data=self.Callback(action=AdminPanelAction.bulk_actions))
            adjust.append(1)

        if can_create_users:
            self.button(text=Texts.create_user, callback_data=self.Callback(action=AdminPanelAction.create_user))
            self.button(
                text=Texts.create_user_from_template,
                callback_data=self.Callback(action=AdminPanelAction.create_user_from_template),
            )
            adjust = adjust + [1, 1]

        self.adjust(*adjust)


class InlineQuerySearch(InlineKeyboardBuilder):
    def __init__(self, query: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.button(text=Texts.search, switch_inline_query_current_chat=query)
