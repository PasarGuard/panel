from app.models.settings import NotificationSettings
from app.models.user import UserNotificationResponse
from app.notification import user_details
from app.notification.client import send_discord_webhook
from app.notification.helpers import get_discord_webhook, group_by_owner, should_send_admin_notification
from app.settings import notification_settings
from app.utils.helpers import escape_ds_markdown

from . import colors, messages
from .utils import escape_md_user, user_changes_md, user_details_md

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
    template: dict,
    user: UserNotificationResponse,
    by: str,
    color: int,
    fields: tuple[str, ...],
    details: str | None = None,
    **extra,
) -> dict:
    username, admin_username, by = escape_md_user(user, by)
    message = {**template, "footer": dict(template["footer"])}
    message["title"] = message["title"].format(status=_status[user.status.value], threshold=extra.get("threshold"))
    message["description"] = message["description"].format(
        username=username, details=user_details_md(user, fields, **extra) if details is None else details
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


async def modify_user(user: UserNotificationResponse, by: str, previous: UserNotificationResponse | None = None):
    details = user_changes_md(user, previous) if previous else None
    data = _build(messages.MODIFY_USER, user, by, colors.YELLOW, user_details.MODIFY, details)
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


async def user_usage_reached(user: UserNotificationResponse, threshold: int):
    data = _build(
        messages.USER_USAGE_REACHED, user, "system", colors.YELLOW, user_details.REMINDER, threshold=threshold
    )
    await _send(user, data, "percentage_reached")


async def user_days_left(user: UserNotificationResponse, threshold: int):
    data = _build(messages.USER_DAYS_LEFT, user, "system", colors.YELLOW, user_details.REMINDER, threshold=threshold)
    await _send(user, data, "days_left")


# kind: (title, owner admin action, color); a status summary uses the status as its title and color.
_DIGEST = {
    "create": ("🆕 Create User", "create", colors.GREEN),
    "modify": ("✏️ Modify User", "modify", colors.YELLOW),
    "remove": ("🗑️ Remove User", "delete", colors.RED),
    "status": (None, "status_change", None),
    "reset_usage": ("🔁 Reset User Data Usage", "reset_data_usage", colors.CYAN),
    "reset_by_next": ("🔁 Reset User", "data_reset_by_next", colors.CYAN),
}


def _build_digest(
    users: list[UserNotificationResponse], kind: str, by: str, reason: str | None, extras: dict[int, dict] | None
) -> dict:
    title, _, color = _DIGEST[kind]
    status = users[0].status.value
    rows, more = user_details.digest_rows(users, kind, extras)
    lines = [
        f"**{escape_ds_markdown(username)}**: "
        + ", ".join(f"{escape_ds_markdown(label)} {escape_ds_markdown(value)}" for label, value in values)
        for username, values in rows
    ]
    lines = user_details.fit_digest_lines(lines, more, lambda count: f"*and {count} more*")
    reason_text = user_details.REASON_LABELS.get(reason, reason) if reason else None
    message = {**messages.USERS_DIGEST, "footer": dict(messages.USERS_DIGEST["footer"])}
    message["title"] = message["title"].format(header=title or _status[status], count=len(users))
    message["description"] = message["description"].format(lines="\n".join(lines))
    message["footer"]["text"] = message["footer"]["text"].format(
        reason=f"Reason: {escape_ds_markdown(reason_text)}\n" if reason_text else "",
        by=escape_ds_markdown(by),
    )
    message["color"] = color if color is not None else _status_color[status]
    return {"content": "", "embeds": [message]}


async def users_digest(
    users: list[UserNotificationResponse],
    kind: str,
    by: str,
    reason: str | None = None,
    extras: dict[int, dict] | None = None,
):
    """One message for many users. A status summary expects users that share one status."""
    _, action, _ = _DIGEST[kind]
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(_build_digest(users, kind, by, reason, extras), webhook)
    for discord_webhook, owned in group_by_owner(users, lambda admin: admin.discord_webhook, action):
        await send_discord_webhook(_build_digest(owned, kind, by, reason, extras), discord_webhook)
