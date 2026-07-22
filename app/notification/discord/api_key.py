from app.models.api_key import APIKeyResponse
from app.models.settings import NotificationSettings
from app.notification.client import send_discord_webhook
from app.notification.helpers import get_discord_webhook
from app.settings import notification_settings

from . import colors, messages

ENTITY = "api_key"


async def create_api_key(api_key: APIKeyResponse, admin_username: str, by: str):
    data = messages.CREATE_API_KEY.copy()
    data["description"] = data["description"].format(
        name=api_key.name,
        expire_date=api_key.expire_date or "Never",
    )
    data["footer"]["text"] = data["footer"]["text"].format(
        id=api_key.id,
        admin_username=admin_username,
        by=by,
    )
    data["color"] = colors.GREEN

    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook_url = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook_url)


async def modify_api_key(api_key: APIKeyResponse, admin_username: str, by: str):
    data = messages.MODIFY_API_KEY.copy()
    data["description"] = data["description"].format(
        name=api_key.name,
        expire_date=api_key.expire_date or "Never",
        status=api_key.status.value,
    )
    data["footer"]["text"] = data["footer"]["text"].format(
        id=api_key.id,
        admin_username=admin_username,
        by=by,
    )
    data["color"] = colors.BLUE

    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook_url = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook_url)


async def remove_api_key(api_key: APIKeyResponse, admin_username: str, by: str):
    data = messages.REMOVE_API_KEY.copy()
    data["description"] = data["description"].format(
        name=api_key.name,
    )
    data["footer"]["text"] = data["footer"]["text"].format(
        id=api_key.id,
        admin_username=admin_username,
        by=by,
    )
    data["color"] = colors.RED

    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook_url = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook_url)
