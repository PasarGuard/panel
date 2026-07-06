from app.notification.client import send_discord_webhook
from app.notification.helpers import get_discord_webhook
from app.models.group import GroupResponse
from app.models.settings import NotificationSettings
from app.settings import notification_settings
from app.utils.helpers import escape_ds_markdown_list, escape_ds_markdown

from . import colors, messages

ENTITY = "group"


async def create_group(group: GroupResponse, by: str):
    name, by = escape_ds_markdown_list((group.name, by))
    message = {**messages.CREATE_GROUP, "footer": dict(messages.CREATE_GROUP["footer"])}
    message["description"] = message["description"].format(
        name=name,
        inbound_tags=group.inbound_tags,
        is_disabled=group.is_disabled,
        status="Disabled" if group.is_disabled else "Enabled",
    )
    message["footer"]["text"] = message["footer"]["text"].format(id=group.id, by=by)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.GREEN
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)


async def modify_group(group: GroupResponse, by: str):
    name, by = escape_ds_markdown_list((group.name, by))
    message = {**messages.MODIFY_GROUP, "footer": dict(messages.MODIFY_GROUP["footer"])}
    message["description"] = message["description"].format(
        name=name,
        inbound_tags=group.inbound_tags,
        is_disabled=group.is_disabled,
        status="Disabled" if group.is_disabled else "Enabled",
    )
    message["footer"]["text"] = message["footer"]["text"].format(id=group.id, by=by)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.YELLOW
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)


async def remove_group(group_id: int, by: str):
    by = escape_ds_markdown(by)
    message = {**messages.REMOVE_GROUP, "footer": dict(messages.REMOVE_GROUP["footer"])}
    message["description"] = message["description"].format(id=group_id)
    message["footer"]["text"] = message["footer"]["text"].format(by=by)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.RED
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)
