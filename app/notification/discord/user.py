from app.models.settings import NotificationSettings
from app.models.user import UserNotificationResponse
from app.notification import user_details
from app.notification.client import send_discord_webhook
from app.notification.helpers import get_discord_webhook, should_send_admin_notification
from app.settings import notification_settings

from . import colors, messages
from .utils import escape_md_user, user_details_md

ENTITY = "user"

_status = {
    "active": "**✅ Activated**",
    "on_hold": "**🕔 On Hold**",
    "disabled": "**❌ Disabled**",
    "limited": "**🪫 Limited**",
    "expired": "**📅 Expired**",
}
_status_color = {
    "active": colors.GREEN,
    "on_hold": colors.PURPLE,
    "disabled": colors.WHITE,
    "limited": colors.RED,
    "expired": colors.YELLOW,
}


def _build(
    template: dict, user: UserNotificationResponse, by: str, color: int, fields: tuple[str, ...], **extra
) -> dict:
    username, admin_username, by = escape_md_user(user, by)
    message = {**template, "footer": dict(template["footer"])}
    message["title"] = message["title"].format(status=_status[user.status.value])
    message["description"] = message["description"].format(
        username=username, details=user_details_md(user, fields, **extra)
    )
    message["footer"]["text"] = message["footer"]["text"].format(id=user.id, admin_username=admin_username, by=by)
    message["color"] = color
    return {"content": "", "embeds": [message]}


async def _send(user: UserNotificationResponse, data: dict, action: str):
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)
    if user.admin and user.admin.discord_webhook and should_send_admin_notification(user.admin, action):
        await send_discord_webhook(data, user.admin.discord_webhook)


async def user_status_change(user: UserNotificationResponse, by: str, reason: str | None = None):
    data = _build(
        messages.USER_STATUS_CHANGE,
        user,
        by,
        _status_color[user.status.value],
        user_details.STATUS_CHANGE,
        reason=reason,
    )
    await _send(user, data, "status_change")


async def create_user(user: UserNotificationResponse, by: str):
    data = _build(messages.CREATE_USER, user, by, colors.GREEN, user_details.CREATE)
    await _send(user, data, "create")


async def modify_user(user: UserNotificationResponse, by: str):
    data = _build(messages.MODIFY_USER, user, by, colors.YELLOW, user_details.MODIFY)
    await _send(user, data, "modify")


async def remove_user(user: UserNotificationResponse, by: str, reason: str | None = None):
    data = _build(messages.REMOVE_USER, user, by, colors.RED, user_details.REMOVE, reason=reason)
    await _send(user, data, "delete")


async def reset_user_data_usage(user: UserNotificationResponse, by: str, reset_traffic: int | None = None):
    data = _build(
        messages.RESET_USER_DATA_USAGE, user, by, colors.CYAN, user_details.RESET_USAGE, reset_traffic=reset_traffic
    )
    await _send(user, data, "reset_data_usage")


async def user_data_reset_by_next(user: UserNotificationResponse, by: str):
    data = _build(messages.USER_DATA_RESET_BY_NEXT, user, by, colors.CYAN, user_details.RESET_BY_NEXT)
    await _send(user, data, "data_reset_by_next")


async def user_subscription_revoked(user: UserNotificationResponse, by: str):
    data = _build(messages.USER_SUBSCRIPTION_REVOKED, user, by, colors.RED, user_details.REVOKE)
    await _send(user, data, "subscription_revoked")
