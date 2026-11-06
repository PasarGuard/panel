"""Plain-text facts about a user for notification messages. Each channel escapes and styles the rows itself."""

from collections.abc import Callable, Iterable
from datetime import UTC, datetime as dt
from enum import StrEnum

from app.db.models import DataLimitResetStrategy, UserStatus
from app.models.user import UserNotificationResponse
from app.utils.system import readable_duration, readable_size


class UserEventReason(StrEnum):
    """Why the system (not an admin) removed or changed a user."""

    expired_autodelete = "expired_autodelete"
    on_hold_timeout = "on_hold_timeout"


REASON_LABELS = {
    UserEventReason.expired_autodelete: "Auto-deleted after expiry",
    UserEventReason.on_hold_timeout: "On-hold timeout passed without use",
}

Row = tuple[str, str]


def relative_time(when: dt, now: dt) -> str:
    seconds = (when - now).total_seconds()
    for label, factor in (("day", 86_400), ("hour", 3_600), ("minute", 60)):
        amount = int(abs(seconds) // factor)
        if amount:
            span = f"{amount} {label}" if amount == 1 else f"{amount} {label}s"
            return f"in {span}" if seconds > 0 else f"{span} ago"
    return "now"


def format_date(when: dt, now: dt) -> str:
    return f"{when.astimezone(UTC):%Y-%m-%d %H:%M} UTC ({relative_time(when, now)})"


def format_usage(used: int, limit: int | None) -> str:
    if not limit:
        return f"{readable_size(used)} / Unlimited"
    return f"{readable_size(used)} / {readable_size(limit)} ({used / limit * 100:.1f}%)"


def format_expire(user: UserNotificationResponse, now: dt) -> str:
    if user.status == UserStatus.on_hold and user.on_hold_expire_duration:
        text = f"{readable_duration(user.on_hold_expire_duration)} after first use"
        if isinstance(user.on_hold_timeout, dt):
            text += f", starts anyway {relative_time(user.on_hold_timeout, now)}"
        return text
    if isinstance(user.expire, dt):
        return format_date(user.expire, now)
    return "Never"


def format_next_plan(user: UserNotificationResponse) -> str | None:
    plan = user.next_plan
    if plan is None:
        return None
    if plan.user_template_id:
        return f"Template #{plan.user_template_id}"
    parts = [
        readable_size(plan.data_limit) if plan.data_limit else "Unlimited",
        readable_duration(plan.expire) if plan.expire else "no expiry",
    ]
    if plan.add_remaining_traffic:
        parts.append("adds remaining traffic")
    return ", ".join(parts)


def _status(user, now, extra):
    return "Status", user.status.value.replace("_", " ").title()


def _data_limit(user, now, extra):
    return "Data Limit", readable_size(user.data_limit) if user.data_limit else "Unlimited"


def _usage(user, now, extra):
    return "Usage", format_usage(user.used_traffic, user.data_limit)


def _cleared(user, now, extra):
    if extra.get("reset_traffic") is None:
        return None
    return "Cleared Usage", readable_size(extra["reset_traffic"])


def _lifetime(user, now, extra):
    return "Lifetime Usage", readable_size(user.lifetime_used_traffic)


def _expire(user, now, extra):
    return "Expire", format_expire(user, now)


def _reset_strategy(user, now, extra):
    strategy = user.data_limit_reset_strategy
    if strategy is None or strategy == DataLimitResetStrategy.no_reset:
        return None
    return "Reset Strategy", strategy.value


def _groups(user, now, extra):
    return ("Groups", ", ".join(user.group_names)) if user.group_names else None


def _next_plan(user, now, extra):
    plan = format_next_plan(user)
    return ("Next Plan", plan) if plan else None


def _created(user, now, extra):
    return "Created", format_date(user.created_at, now)


def _online(user, now, extra):
    return "Last Online", relative_time(user.online_at, now) if user.online_at else "Never"


def _note(user, now, extra):
    return ("Note", user.note) if user.note else None


def _reason(user, now, extra):
    reason = extra.get("reason")
    return ("Reason", REASON_LABELS.get(reason, str(reason))) if reason else None


_FIELDS: dict[str, Callable[[UserNotificationResponse, dt, dict], Row | None]] = {
    "reason": _reason,
    "status": _status,
    "data_limit": _data_limit,
    "usage": _usage,
    "cleared": _cleared,
    "lifetime": _lifetime,
    "expire": _expire,
    "reset_strategy": _reset_strategy,
    "groups": _groups,
    "next_plan": _next_plan,
    "created": _created,
    "online": _online,
    "note": _note,
}

# The rows each user event shows, in order.
CREATE = ("data_limit", "expire", "reset_strategy", "groups", "next_plan", "note")
MODIFY = ("status", "usage", "expire", "reset_strategy", "groups", "next_plan", "note")
STATUS_CHANGE = ("reason", "usage", "expire", "online")
REMOVE = ("reason", "status", "usage", "lifetime", "expire", "created", "online", "groups", "note")
RESET_USAGE = ("cleared", "data_limit", "lifetime", "expire")
RESET_BY_NEXT = ("usage", "expire", "next_plan")
REVOKE = ("status", "usage", "expire")


def user_rows(user: UserNotificationResponse, fields: Iterable[str], now: dt | None = None, **extra) -> list[Row]:
    now = now or dt.now(UTC)
    rows = (_FIELDS[name](user, now, extra) for name in fields)
    return [row for row in rows if row is not None]
