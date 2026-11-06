"""User notifications carry the user's state: usage, expiry, lifetime traffic and why the system acted."""

from datetime import UTC, datetime as dt, timedelta as td
from types import SimpleNamespace

import pytest

from app.db.models import DataLimitResetStrategy, UserStatus
from app.models.user import UserNotificationResponse
from app.notification import user_details, webhook as wh
from app.notification.discord import user as ds_user
from app.notification.telegram import user as tg_user
from app.notification.user_details import UserEventReason

GB = 1024**3
NOW = dt(2026, 11, 6, 12, 0, tzinfo=UTC)


def _user(**overrides) -> UserNotificationResponse:
    data = {
        "id": 7,
        "username": "alice",
        "status": UserStatus.expired,
        "used_traffic": 3 * GB,
        "lifetime_used_traffic": 25 * GB,
        "data_limit": 10 * GB,
        "data_limit_reset_strategy": DataLimitResetStrategy.month,
        "expire": NOW - td(days=2),
        "created_at": NOW - td(days=40),
        "online_at": NOW - td(hours=5),
        "group_names": ["vip"],
        "note": "<b>paid</b>",
    } | overrides
    return UserNotificationResponse(**data)


def test_rows_for_removed_user():
    rows = dict(
        user_details.user_rows(_user(), user_details.REMOVE, now=NOW, reason=UserEventReason.expired_autodelete)
    )

    assert rows == {
        "Reason": "Auto-deleted after expiry",
        "Status": "Expired",
        "Usage": "3.0 GB / 10.0 GB (30.0%)",
        "Lifetime Usage": "25.0 GB",
        "Expire": "2026-11-04 12:00 UTC (2 days ago)",
        "Created": "2026-09-27 12:00 UTC (40 days ago)",
        "Last Online": "5 hours ago",
        "Groups": "vip",
        "Note": "<b>paid</b>",
    }


def test_rows_skip_empty_values():
    user = _user(
        status=UserStatus.active,
        data_limit=None,
        expire=None,
        online_at=None,
        group_names=[],
        note=None,
        data_limit_reset_strategy=DataLimitResetStrategy.no_reset,
    )
    rows = dict(user_details.user_rows(user, user_details.MODIFY, now=NOW))

    assert rows == {"Status": "Active", "Usage": "3.0 GB / Unlimited", "Expire": "Never"}


def test_on_hold_expire_shows_duration_and_timeout():
    user = _user(
        status=UserStatus.on_hold,
        expire=None,
        on_hold_expire_duration=30 * 86400,
        on_hold_timeout=NOW + td(days=3, hours=1),
    )

    assert user_details.format_expire(user, NOW) == "1 month after first use, starts anyway in 3 days"


def test_next_plan_and_cleared_usage():
    user = _user(next_plan={"data_limit": 50 * GB, "expire": 86400 * 7, "add_remaining_traffic": True})

    assert dict(user_details.user_rows(user, ("next_plan", "cleared"), now=NOW, reset_traffic=4 * GB)) == {
        "Next Plan": "50.0 GB, 7 days, adds remaining traffic",
        "Cleared Usage": "4.0 GB",
    }


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch):
    messages = []
    settings = SimpleNamespace(notify_telegram=True, notify_discord=True)

    async def notification_settings():
        return settings

    async def send_telegram_message(data, chat_id=None, topic_id=None):
        messages.append(data)

    async def send_discord_webhook(data, webhook):
        messages.append(data)

    for module in (tg_user, ds_user):
        monkeypatch.setattr(module, "notification_settings", notification_settings)
    monkeypatch.setattr(tg_user, "send_telegram_message", send_telegram_message)
    monkeypatch.setattr(tg_user, "get_telegram_channel", lambda settings, entity: (1, None))
    monkeypatch.setattr(ds_user, "send_discord_webhook", send_discord_webhook)
    monkeypatch.setattr(ds_user, "get_discord_webhook", lambda settings, entity: "https://discord.invalid/hook")
    return messages


async def test_telegram_remove_message_has_details_and_escapes(sent):
    await tg_user.remove_user(_user(), "system", UserEventReason.on_hold_timeout)

    (text,) = sent
    assert "#Remove_User" in text
    assert "<b>Reason:</b> <code>On-hold timeout passed without use</code>" in text
    assert "<b>Usage:</b> <code>3.0 GB / 10.0 GB (30.0%)</code>" in text
    assert "<b>Lifetime Usage:</b> <code>25.0 GB</code>" in text
    assert "<b>Note:</b> <code>&lt;b&gt;paid&lt;/b&gt;</code>" in text
    assert "<b>paid</b>" not in text


async def test_discord_status_change_has_details(sent):
    await ds_user.user_status_change(_user(status=UserStatus.limited, note="*x*"), "system")

    (data,) = sent
    embed = data["embeds"][0]
    assert embed["title"] == "**🪫 Limited**"
    assert "**Usage:** 3.0 GB / 10.0 GB (30.0%)" in embed["description"]
    assert "Reason" not in embed["description"]


async def test_telegram_reset_shows_cleared_usage(sent):
    await tg_user.reset_user_data_usage(_user(used_traffic=0), "admin", 3 * GB)

    assert "<b>Cleared Usage:</b> <code>3.0 GB</code>" in sent[0]


def test_webhook_next_plan_reset_has_its_own_type_and_an_id():
    user = _user()
    first = wh.UserDataResetByNext(username=user.username, user=user)
    second = wh.UserDataResetByNext(username=user.username, user=user)

    assert first.action == wh.Notification.Type.data_reset_by_next
    assert first.id and first.id != second.id


def test_webhook_deleted_carries_reason():
    user = _user()
    payload = wh.UserDeleted(
        username=user.username,
        user=user,
        by={"username": "system", "is_sudo": True},
        reason=UserEventReason.expired_autodelete,
    ).model_dump(mode="json")

    assert payload["reason"] == "expired_autodelete"
