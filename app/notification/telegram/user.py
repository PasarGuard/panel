import html

from app.models.settings import NotificationSettings
from app.models.user import UserNotificationResponse
from app.notification import user_details
from app.notification.client import send_telegram_message
from app.notification.helpers import get_telegram_channel, group_by_owner, should_send_admin_notification
from app.settings import notification_settings

from . import messages
from .utils import escape_html_user, user_changes_html, user_details_html

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


def _format(
    template: str, user: UserNotificationResponse, by: str, fields: tuple[str, ...], details: str | None = None, **extra
) -> str:
    username, admin_username, by = escape_html_user(user, by)
    return template.format(
        username=username,
        details=user_details_html(user, fields, **extra) if details is None else details,
        admin_username=admin_username,
        by=by,
        status=_status[user.status.value],
        threshold=extra.get("threshold"),
    )


async def user_status_change(user: UserNotificationResponse, by: str, reason: str | None = None):
    data = _format(messages.USER_STATUS_CHANGE, user, by, user_details.STATUS_CHANGE, reason=reason)
    await _send(user, data, "status_change")


async def create_user(user: UserNotificationResponse, by: str):
    data = _format(messages.CREATE_USER, user, by, user_details.CREATE)
    await _send(user, data, "create")


async def modify_user(user: UserNotificationResponse, by: str, previous: UserNotificationResponse | None = None):
    details = user_changes_html(user, previous) if previous else None
    data = _format(messages.MODIFY_USER, user, by, user_details.MODIFY, details)
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


# kind: (header, owner admin action); a status summary uses the status as its header.
_DIGEST = {
    "create": ("🆕 #Create_User", "create"),
    "modify": ("✏️ #Modify_User", "modify"),
    "remove": ("🗑️ #Remove_User", "delete"),
    "status": (None, "status_change"),
    "reset_usage": ("🔁 #Reset_User_Data_Usage", "reset_data_usage"),
    "reset_by_next": ("🔁 #Reset_User_By_Next", "data_reset_by_next"),
    "usage_reminder": ("⚠️ #Usage_Reminder", "percentage_reached"),
    "expiry_reminder": ("⏳ #Expiry_Reminder", "days_left"),
}


def _format_digest(
    users: list[UserNotificationResponse], kind: str, by: str, reason: str | None, extras: dict[int, dict] | None
) -> str:
    header, _ = _DIGEST[kind]
    rows, more = user_details.digest_rows(users, kind, extras)
    lines = [
        f"<code>{html.escape(username)}</code>: "
        + ", ".join(f"{html.escape(label)} {html.escape(value)}" for label, value in values)
        for username, values in rows
    ]
    lines = user_details.fit_digest_lines(lines, more, lambda count: f"<i>and {count} more</i>")
    reason_text = user_details.REASON_LABELS.get(reason, reason) if reason else None
    return messages.USERS_DIGEST.format(
        header=header or _status[users[0].status.value],
        count=len(users),
        lines="\n".join(lines),
        reason=f"<i>Reason: {html.escape(reason_text)}</i>\n" if reason_text else "",
        by=html.escape(by),
    )


async def users_digest(
    users: list[UserNotificationResponse],
    kind: str,
    by: str,
    reason: str | None = None,
    extras: dict[int, dict] | None = None,
):
    """One message for many users. A status summary expects users that share one status."""
    _, action = _DIGEST[kind]
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(_format_digest(users, kind, by, reason, extras), chat_id, topic_id)
    for telegram_id, owned in group_by_owner(users, lambda admin: admin.telegram_id, action):
        await send_telegram_message(_format_digest(owned, kind, by, reason, extras), chat_id=telegram_id)
