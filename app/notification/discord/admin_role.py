import copy

from app.notification.client import send_discord_webhook
from app.notification.helpers import get_discord_webhook
from app.models.admin_role import AdminRoleResponse
from app.models.settings import NotificationSettings
from app.settings import notification_settings
from app.utils.helpers import escape_ds_markdown_list

from . import colors, messages

ENTITY = "admin_role"


async def create_admin_role(role: AdminRoleResponse, by: str):
    name, by = escape_ds_markdown_list((role.name, by))
    message = copy.deepcopy(messages.CREATE_ADMIN_ROLE)
    message["description"] = message["description"].format(name=name, is_owner=role.is_owner)
    message["footer"]["text"] = message["footer"]["text"].format(id=role.id, by=by)
    data = {"content": "", "embeds": [message]}
    data["embeds"][0]["color"] = colors.GREEN
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)


async def modify_admin_role(role: AdminRoleResponse, by: str):
    name, by = escape_ds_markdown_list((role.name, by))
    message = copy.deepcopy(messages.MODIFY_ADMIN_ROLE)
    message["description"] = message["description"].format(name=name, is_owner=role.is_owner)
    message["footer"]["text"] = message["footer"]["text"].format(id=role.id, by=by)
    data = {"content": "", "embeds": [message]}
    data["embeds"][0]["color"] = colors.YELLOW
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)


async def remove_admin_role(role: AdminRoleResponse, by: str):
    name, by = escape_ds_markdown_list((role.name, by))
    message = copy.deepcopy(messages.REMOVE_ADMIN_ROLE)
    message["description"] = message["description"].format(name=name)
    message["footer"]["text"] = message["footer"]["text"].format(id=role.id, by=by)
    data = {"content": "", "embeds": [message]}
    data["embeds"][0]["color"] = colors.RED
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)
