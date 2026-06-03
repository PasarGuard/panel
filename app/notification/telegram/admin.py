from app.models.admin import AdminDetails
from app.models.settings import NotificationSettings
from app.notification.client import send_telegram_message
from app.notification.helpers import get_telegram_channel
from app.settings import notification_settings
from app.utils.helpers import escape_tg_html
from app.utils.system import readable_size

from . import messages

ENTITY = "admin"


async def create_admin(admin: AdminDetails, by: str):
    username, by = escape_tg_html((admin.username, by))
    role = admin.role.name if admin.role else "unknown"
    data = messages.CREATE_ADMIN.format(
        username=username,
        role=role,
        status=admin.status.value,
        used_traffic=readable_size(admin.used_traffic),
        by=by,
    )
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)


async def modify_admin(admin: AdminDetails, by: str):
    username, by = escape_tg_html((admin.username, by))
    role = admin.role.name if admin.role else "unknown"
    data = messages.MODIFY_ADMIN.format(
        username=username,
        role=role,
        status=admin.status.value,
        used_traffic=readable_size(admin.used_traffic),
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


async def admin_usage_limit_reached(admin: AdminDetails, usage_percentage: int, threshold: int):
    username = escape_tg_html((admin.username,))[0]
    data = messages.ADMIN_USAGE_LIMIT_REACHED.format(
        username=username,
        used_traffic=readable_size(admin.used_traffic),
        data_limit=readable_size(admin.data_limit) if admin.data_limit else "Unlimited",
        usage_percentage=usage_percentage,
        threshold=threshold,
    )
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram and admin.telegram_id:
        await send_telegram_message(data, chat_id=admin.telegram_id)


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
