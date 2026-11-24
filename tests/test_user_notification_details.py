"""User notifications carry the user's state: usage, expiry, lifetime traffic and why the system acted."""

import asyncio
from contextlib import asynccontextmanager as asynccontextmanager_db
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


def test_change_rows_list_only_changed_fields():
    old = _user(data_limit=10 * GB, group_names=["vip"], note=None)
    new = _user(data_limit=20 * GB, group_names=["vip", "eu"], note="renewed")

    assert user_details.change_rows(old, new, user_details.MODIFY_DIFF, now=NOW) == [
        ("data_limit", "Data Limit", "10.0 GB", "20.0 GB"),
        ("groups", "Groups", "vip", "vip, eu"),
        ("note", "Note", "None", "renewed"),
    ]


async def test_telegram_modify_shows_changes_then_current_state(sent):
    await tg_user.modify_user(_user(data_limit=20 * GB), "admin", previous=_user())

    (text,) = sent
    assert "<b>Data Limit:</b> <code>10.0 GB</code> → <code>20.0 GB</code>" in text
    assert "<b>Usage:</b> <code>3.0 GB / 20.0 GB (15.0%)</code>" in text
    assert "Reset Strategy" not in text


def test_notification_snapshot_skips_unloaded_relations():
    from app.operation.user import UserOperation

    loaded = SimpleNamespace(
        id=7,
        username="alice",
        status=UserStatus.active,
        used_traffic=0,
        data_limit=GB,
        data_limit_reset_strategy=DataLimitResetStrategy.no_reset,
        expire=None,
        note=None,
        on_hold_expire_duration=None,
        on_hold_timeout=None,
        created_at=NOW,
        online_at=None,
        group_names=["vip"],
        next_plan=None,
    )
    loaded.groups = []
    snapshot = UserOperation.notification_snapshot(loaded)
    assert snapshot is not None and snapshot.group_names == ["vip"] and snapshot.data_limit == GB

    del loaded.groups
    assert UserOperation.notification_snapshot(loaded) is None


def _owned(user_id: int, admin_username: str | None, telegram_id: int | None = None, **overrides):
    admin = {"username": admin_username, "telegram_id": telegram_id} if admin_username else None
    return _user(id=user_id, username=f"user{user_id}", admin=admin, **overrides)


async def test_digest_sends_one_message_per_channel_and_owner(sent):
    users = [_owned(i, "reseller", telegram_id=55) for i in range(4)] + [_owned(i, None) for i in range(4, 8)]

    await tg_user.users_digest(users, "remove", "system", UserEventReason.expired_autodelete)

    channel, owner = sent
    assert "#Remove_User <b>8 users</b>" in channel
    assert "<code>user0</code>: Usage 3.0 GB / 10.0 GB (30.0%), Expire" in channel
    assert "Reason: Auto-deleted after expiry" in channel
    assert "<b>4 users</b>" in owner and "user4" not in owner


async def test_digest_caps_lines(sent):
    users = [_owned(i, None) for i in range(user_details.DIGEST_MAX_LINES + 5)]

    await ds_user.users_digest(users, "status", "system")

    embed = sent[0]["embeds"][0]
    assert embed["title"] == f"**📅 Expired** ({len(users)} users)"
    assert embed["description"].endswith("*and 5 more*")


async def test_bulk_dispatch_uses_singles_below_threshold_and_digest_above(monkeypatch):
    from app import notification

    calls = []

    async def enabled():
        return SimpleNamespace(user=SimpleNamespace(delete=True))

    async def single(user, by, reason=None):
        calls.append(("single", user.username))

    async def digest(users, kind, by, reason=None, extras=None):
        calls.append(("digest", len(users)))

    async def bulk_notify(messages):
        calls.append(("webhooks", len(messages)))

    monkeypatch.setattr(notification, "notification_enable", enabled)
    monkeypatch.setattr(notification, "remove_user", single)
    monkeypatch.setattr(notification.tg, "users_digest", digest)
    monkeypatch.setattr(notification.ds, "users_digest", digest)
    monkeypatch.setattr(notification.wh, "bulk_notify", bulk_notify)
    by = SimpleNamespace(username="system")

    await notification.bulk_remove_users([_owned(i, None) for i in range(2)], by)
    assert calls == [("single", "user0"), ("single", "user1")]

    calls.clear()
    many = [_owned(i, None) for i in range(user_details.DIGEST_MIN_USERS)]
    monkeypatch.setattr(notification.wh, "UserDeleted", lambda **kwargs: kwargs)
    await notification.bulk_remove_users(many, by)
    assert sorted(calls) == [("digest", len(many)), ("digest", len(many)), ("webhooks", len(many))]


def _reminder_owner(telegram_id: int = 55, **preferences):
    return {
        "username": "reseller",
        "telegram_id": telegram_id,
        "notification_enable": preferences or None,
    }


async def test_usage_reminder_is_one_summary_with_each_users_threshold(sent):
    users = [_owned(1, None, status=UserStatus.active), _owned(2, None, status=UserStatus.active)]

    await tg_user.users_digest(users, "usage_reminder", "system", None, {1: {"threshold": 80}, 2: {"threshold": 90}})

    assert len(sent) == 1
    assert "#Usage_Reminder" in sent[0]
    assert "<b>2 users</b>" in sent[0]
    assert "Reached 80%" in sent[0]
    assert "Reached 90%" in sent[0]


async def test_expiry_reminder_reaches_discord(sent):
    users = [_owned(1, None, status=UserStatus.active, expire=NOW + td(days=3))]

    await ds_user.users_digest(users, "expiry_reminder", "system")

    assert "Expiry Reminder" in sent[0]["embeds"][0]["title"]


@pytest.mark.parametrize(
    ("preferences", "owner_messages"),
    [({}, 0), ({"create": True}, 0), ({"percentage_reached": False}, 0), ({"percentage_reached": True}, 1)],
)
async def test_owner_dm_for_reminders_is_opt_in(sent, preferences, owner_messages):
    user = _user(status=UserStatus.active, admin=_reminder_owner(**preferences))

    await tg_user.users_digest([user], "usage_reminder", "system", None, {user.id: {"threshold": 80}})

    assert len(sent) == 1 + owner_messages


def test_reminder_preferences_do_not_change_other_owner_notifications():
    from app.notification.helpers import should_send_admin_notification

    admin = SimpleNamespace(notification_enable=None)

    assert should_send_admin_notification(admin, "create") is True
    assert should_send_admin_notification(admin, "percentage_reached") is False
    assert should_send_admin_notification(admin, "days_left") is False


def _reminder_job(monkeypatch, *, webhook_enable=False, enable=None, channels=None, users=None):
    """Runs the usage job against fakes; `users` maps (threshold, for_chat) to db users."""
    from app.jobs import review_users
    from app.models.notification_enable import NotificationEnable

    summaries, webhooks, recorded, lookups = [], [], [], []
    users = users or {}

    async def webhook_settings():
        return SimpleNamespace(enable=webhook_enable, usage_percent=[50], days_left=[])

    async def notification_settings():
        return channels or SimpleNamespace(notify_telegram=True, notify_discord=False)

    async def notification_enable():
        return enable or NotificationEnable()

    async def user_reminders(models, kind, extras=None):
        summaries.append(([model.id for model in models], kind, extras))

    async def bulk_notify(messages):
        webhooks.extend(messages)

    async def users_at(db, percent, for_chat=False):
        lookups.append((percent, for_chat))
        return users.get((percent, for_chat), [])

    @asynccontextmanager_db
    async def get_db():
        yield None

    async def create_reminders(db, data):
        recorded.extend(data)

    monkeypatch.setattr(review_users, "webhook_settings", webhook_settings)
    monkeypatch.setattr(review_users, "notification_settings", notification_settings)
    monkeypatch.setattr(review_users, "notification_enable", notification_enable)
    monkeypatch.setattr(review_users, "get_usage_percentage_reached_users", users_at)
    monkeypatch.setattr(review_users, "bulk_create_notification_reminders", create_reminders)
    monkeypatch.setattr(review_users, "GetDB", get_db)
    monkeypatch.setattr(
        review_users.UserNotificationResponse,
        "model_validate",
        lambda user: _user(id=user.id, status=UserStatus.active),
    )
    monkeypatch.setattr(review_users.notification, "user_reminders", user_reminders)
    monkeypatch.setattr(review_users.notification.wh, "bulk_notify", bulk_notify)
    return review_users, SimpleNamespace(summaries=summaries, webhooks=webhooks, recorded=recorded, lookups=lookups)


def _db_user(user_id: int):
    return SimpleNamespace(id=user_id, usage_percentage=95.0, expire=None)


async def test_chat_reminders_are_off_by_default(monkeypatch):
    from app.models.notification_enable import NotificationEnable

    defaults = NotificationEnable()
    assert (defaults.days_left, defaults.percentage_reached) == (False, False)
    assert (defaults.days_left_thresholds, defaults.percentage_reached_thresholds) == ([], [])

    job, seen = _reminder_job(monkeypatch)
    await job.usage_percent_notification_job()

    assert seen.lookups == []


async def test_chat_reminder_lists_user_once_at_highest_threshold(monkeypatch):
    from app.models.notification_enable import NotificationEnable

    enable = NotificationEnable(percentage_reached=True, percentage_reached_thresholds=[90, 80])
    job, seen = _reminder_job(
        monkeypatch,
        enable=enable,
        users={(80, True): [_db_user(1), _db_user(2)], (90, True): [_db_user(1)]},
    )

    await job.usage_percent_notification_job()
    await asyncio.sleep(0)

    assert seen.summaries == [([1, 2], "usage_reminder", {1: {"threshold": 90}, 2: {"threshold": 80}})]
    # Every crossed threshold is recorded, so the lower one does not send later.
    assert sorted((row["user_id"], row["threshold"], row["for_chat"]) for row in seen.recorded) == [
        (1, 80, True),
        (1, 90, True),
        (2, 80, True),
    ]


async def test_webhook_thresholds_do_not_reach_chat(monkeypatch):
    from app.models.notification_enable import NotificationEnable

    enable = NotificationEnable(percentage_reached=True, percentage_reached_thresholds=[80])
    job, seen = _reminder_job(monkeypatch, webhook_enable=True, enable=enable, users={(50, False): [_db_user(1)]})
    monkeypatch.setattr(job.notification.wh, "ReachedUsagePercent", lambda **kwargs: kwargs)

    await job.usage_percent_notification_job()
    await asyncio.sleep(0)

    assert seen.lookups == [(50, False), (80, True)]
    assert len(seen.webhooks) == 1
    assert seen.summaries == []


async def test_chat_reminders_need_a_chat_channel(monkeypatch):
    from app.models.notification_enable import NotificationEnable

    job, seen = _reminder_job(
        monkeypatch,
        enable=NotificationEnable(percentage_reached=True, percentage_reached_thresholds=[80]),
        channels=SimpleNamespace(notify_telegram=False, notify_discord=False),
    )

    await job.usage_percent_notification_job()

    assert seen.lookups == []


@pytest.mark.parametrize("field", ["days_left_thresholds", "percentage_reached_thresholds"])
def test_reminder_thresholds_are_sorted_and_validated(field):
    from pydantic import ValidationError

    from app.models.notification_enable import NotificationEnable

    assert getattr(NotificationEnable(**{field: [9, 3, 9]}), field) == [3, 9]
    with pytest.raises(ValidationError):
        NotificationEnable(**{field: [0]})


@pytest.mark.parametrize(
    ("password", "masked"),
    [("hunter2", "******* (7 chars)"), ("correct-horse", "c***********e (13 chars)"), ("", " (0 chars)")],
)
def test_mask_password(password, masked):
    from app.notification.helpers import mask_password

    assert mask_password(password) == masked


async def test_digest_stays_under_the_message_limit(sent):
    users = [_user(id=i, username=f"{'x' * 200}{i}") for i in range(user_details.DIGEST_MAX_LINES)]

    await tg_user.users_digest(users, "remove", "system")

    (text,) = sent
    assert len(text) < 4096
    shown = text.count("<code>x")
    assert 0 < shown < len(users)
    assert f"<i>and {len(users) - shown} more</i>" in text


async def test_bulk_status_change_counts_the_whole_action(monkeypatch):
    from app import notification

    digests = []

    async def enabled():
        return SimpleNamespace(user=SimpleNamespace(status_change=True))

    async def digest(users, kind, by, reason=None, extras=None):
        digests.append(sorted({user.status.value for user in users}))

    async def bulk_notify(messages):
        pass

    monkeypatch.setattr(notification, "notification_enable", enabled)
    monkeypatch.setattr(notification.tg, "users_digest", digest)
    monkeypatch.setattr(notification.ds, "users_digest", digest)
    monkeypatch.setattr(notification.wh, "bulk_notify", bulk_notify)
    users = [_owned(i, None, status=UserStatus.active) for i in range(3)] + [
        _owned(i, None, status=UserStatus.limited) for i in range(3, 6)
    ]

    await notification.bulk_user_status_change(users, SimpleNamespace(username="system"))

    assert sorted(digests) == [["active"], ["active"], ["limited"], ["limited"]]


async def test_bulk_modify_passes_previous_state(monkeypatch):
    from app import notification

    seen = []

    async def enabled():
        return SimpleNamespace(user=SimpleNamespace(modify=True))

    async def single(user, by, previous=None):
        seen.append(previous.data_limit if previous else None)

    monkeypatch.setattr(notification, "notification_enable", enabled)
    monkeypatch.setattr(notification, "modify_user", single)
    users = [_owned(1, None), _owned(2, None)]

    await notification.bulk_modify_users(users, SimpleNamespace(username="a"), {1: _owned(1, None, data_limit=GB)})

    assert seen == [GB, None]
