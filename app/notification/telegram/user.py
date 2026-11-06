from app.models.settings import NotificationSettings
from app.models.user import UserNotificationResponse
from app.notification import user_details
from app.notification.client import send_telegram_message
from app.notification.helpers import get_telegram_channel, should_send_admin_notification
from app.settings import notification_settings

from . import messages
from .utils import escape_html_user, user_details_html

ENTITY = "user"

_status = {
    "active": "<b>✅ #Activated</b>",
    "on_hold": "<b>🕔 #On_Hold</b>",
    "disabled": "<b>❌ #Disabled</b>",
    "limited": "<b>🪫 #Limited</b>",
    "expired": "<b>📅 #Expired</b>",
}


async def _send(user: UserNotificationResponse, data: str, action: str):
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)
    if user.admin and user.admin.telegram_id and should_send_admin_notification(user.admin, action):
        await send_telegram_message(data, chat_id=user.admin.telegram_id)


def _format(template: str, user: UserNotificationResponse, by: str, fields: tuple[str, ...], **extra) -> str:
    username, admin_username, by = escape_html_user(user, by)
    return template.format(
        username=username,
        details=user_details_html(user, fields, **extra),
        admin_username=admin_username,
        by=by,
        status=_status[user.status.value],
    )


async def user_status_change(user: UserNotificationResponse, by: str, reason: str | None = None):
    data = _format(messages.USER_STATUS_CHANGE, user, by, user_details.STATUS_CHANGE, reason=reason)
    await _send(user, data, "status_change")


async def create_user(user: UserNotificationResponse, by: str):
    data = _format(messages.CREATE_USER, user, by, user_details.CREATE)
    await _send(user, data, "create")


async def modify_user(user: UserNotificationResponse, by: str):
    data = _format(messages.MODIFY_USER, user, by, user_details.MODIFY)
    await _send(user, data, "modify")


async def remove_user(user: UserNotificationResponse, by: str, reason: str | None = None):
    data = _format(messages.REMOVE_USER, user, by, user_details.REMOVE, reason=reason)
    await _send(user, data, "delete")


async def reset_user_data_usage(user: UserNotificationResponse, by: str, reset_traffic: int | None = None):
    data = _format(messages.RESET_USER_DATA_USAGE, user, by, user_details.RESET_USAGE, reset_traffic=reset_traffic)
    await _send(user, data, "reset_data_usage")


async def user_data_reset_by_next(user: UserNotificationResponse, by: str):
    data = _format(messages.USER_DATA_RESET_BY_NEXT, user, by, user_details.RESET_BY_NEXT)
    await _send(user, data, "data_reset_by_next")


async def user_subscription_revoked(user: UserNotificationResponse, by: str):
    data = _format(messages.USER_SUBSCRIPTION_REVOKED, user, by, user_details.REVOKE)
    await _send(user, data, "subscription_revoked")
