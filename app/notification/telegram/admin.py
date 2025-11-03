from app.notification.client import send_telegram_message
from app.notification.helpers import get_telegram_channel
from app.models.admin import AdminDetails
from app.models.settings import NotificationSettings
from app.settings import notification_settings
from app.utils.helpers import escape_tg_html
from . import messages

ENTITY = "admin"


async def create_admin(admin: AdminDetails, by: str):
    username, by = escape_tg_html((admin.username, by))
    data = messages.CREATE_ADMIN.format(
        username=username,
        is_sudo=admin.is_sudo,
        is_disabled=admin.is_disabled,
        used_traffic=admin.used_traffic,
        by=by,
    )
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)


async def modify_admin(admin: AdminDetails, by: str):
    username, by = escape_tg_html((admin.username, by))
    data = messages.MODIFY_ADMIN.format(
        username=username,
        is_sudo=admin.is_sudo,
        is_disabled=admin.is_disabled,
        used_traffic=admin.used_traffic,
        by=by,
    )
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)


async def remove_admin(username: str, by: str):
    username, by = escape_tg_html((username, by))
    data = messages.REMOVE_ADMIN.format(username=username, by=by)
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)


async def admin_reset_usage(admin: AdminDetails, by: str):
    username, by = escape_tg_html((admin.username, by))
    data = messages.ADMIN_RESET_USAGE.format(username=username, by=by)
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)


async def admin_login(username: str, password: str, client_ip: str, success: bool):
    username, password = escape_tg_html((username, password))
    data = messages.ADMIN_LOGIN.format(
        status="Successful" if success else "Failed",
        username=username,
        password="🔒" if success else password,
        client_ip=client_ip,
    )
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)
