from app.models.admin import AdminDetails
from app.models.settings import NotificationSettings
from app.notification.client import send_discord_webhook
from app.notification.helpers import get_discord_webhook
from app.settings import notification_settings
from app.utils.helpers import escape_ds_markdown_list
from app.utils.system import readable_size

from . import colors, messages

ENTITY = "admin"


async def create_admin(admin: AdminDetails, by: str):
    username, by = escape_ds_markdown_list((admin.username, by))
    message = {**messages.CREATE_ADMIN, "footer": dict(messages.CREATE_ADMIN["footer"])}
    role = admin.role.name if admin.role else "unknown"
    message["description"] = message["description"].format(
        username=username,
        role=role,
        status=admin.status.value,
        used_traffic=admin.used_traffic,
    )
    message["footer"]["text"] = message["footer"]["text"].format(by=by)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.GREEN
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)


async def modify_admin(admin: AdminDetails, by: str):
    username, by = escape_ds_markdown_list((admin.username, by))
    message = {**messages.MODIFY_ADMIN, "footer": dict(messages.MODIFY_ADMIN["footer"])}
    role = admin.role.name if admin.role else "unknown"
    message["description"] = message["description"].format(
        username=username,
        role=role,
        status=admin.status.value,
        used_traffic=admin.used_traffic,
    )
    message["footer"]["text"] = message["footer"]["text"].format(by=by)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.YELLOW
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)


async def remove_admin(username: str, by: str):
    username, by = escape_ds_markdown_list((username, by))
    message = {**messages.REMOVE_ADMIN, "footer": dict(messages.REMOVE_ADMIN["footer"])}
    message["description"] = message["description"].format(username=username)
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


async def admin_reset_usage(admin: AdminDetails, by: str):
    username, by = escape_ds_markdown_list((admin.username, by))
    message = {**messages.ADMIN_RESET_USAGE, "footer": dict(messages.ADMIN_RESET_USAGE["footer"])}
    message["description"] = message["description"].format(username=username)
    message["footer"]["text"] = message["footer"]["text"].format(by=by)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.CYAN
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)


async def admin_usage_limit_reached(admin: AdminDetails, usage_percentage: int, threshold: int):
    username = escape_ds_markdown_list((admin.username,))[0]
    message = {**messages.ADMIN_USAGE_LIMIT_REACHED}
    message["description"] = message["description"].format(
        username=username,
        used_traffic=readable_size(admin.used_traffic),
        data_limit=readable_size(admin.data_limit) if admin.data_limit else "Unlimited",
        usage_percentage=usage_percentage,
        threshold=threshold,
    )
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.YELLOW
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord and admin.discord_webhook:
        await send_discord_webhook(data, admin.discord_webhook)


async def admin_login(username: str, password: str, client_ip: str, success: bool):
    username, password = escape_ds_markdown_list((username, password))
    message = {**messages.ADMIN_LOGIN, "footer": dict(messages.ADMIN_LOGIN["footer"])}
    message["description"] = message["description"].format(
        username=username,
        password="🔒" if success else password,
        client_ip=client_ip,
    )
    message["footer"]["text"] = message["footer"]["text"].format(status="Successful" if success else "Failed")
    data = {
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.GREEN if success else colors.RED
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)
