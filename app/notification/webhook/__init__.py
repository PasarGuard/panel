from datetime import UTC, datetime as dt
from enum import Enum
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.models.admin import AdminDetails
from app.models.user import UserNotificationResponse, UserStatus
from app.notification.queue_manager import enqueue_webhook
from app.settings import webhook_settings


def get_current_timestamp() -> float:
    """Factory function to get current timestamp"""
    return dt.now(UTC).timestamp()


class Notification(BaseModel):
    class Type(str, Enum):
        user_created = "user_created"
        user_updated = "user_updated"
        user_deleted = "user_deleted"
        user_limited = "user_limited"
        user_expired = "user_expired"
        user_enabled = "user_enabled"
        user_disabled = "user_disabled"
        data_usage_reset = "data_usage_reset"
        data_reset_by_next = "data_reset_by_next"
        subscription_revoked = "subscription_revoked"

        reached_usage_percent = "reached_usage_percent"
        reached_days_left = "reached_days_left"

    # Stays the same across delivery retries, so receivers can drop repeats.
    id: str = Field(default_factory=lambda: uuid4().hex)
    enqueued_at: float = Field(default_factory=get_current_timestamp)
    send_at: float = Field(default_factory=get_current_timestamp)
    tries: int = Field(default=0)


class UserNotification(Notification):
    username: str


class ReachedUsagePercent(UserNotification):
    action: Notification.Type = Notification.Type.reached_usage_percent
    user: UserNotificationResponse
    used_percent: float


class ReachedDaysLeft(UserNotification):
    action: Notification.Type = Notification.Type.reached_days_left
    user: UserNotificationResponse
    days_left: int


class UserCreated(UserNotification):
    action: Notification.Type = Notification.Type.user_created
    by: AdminDetails
    user: UserNotificationResponse


class UserUpdated(UserNotification):
    action: Notification.Type = Notification.Type.user_updated
    by: AdminDetails
    user: UserNotificationResponse
    # The user before the change, when the caller captured it.
    previous: UserNotificationResponse | None = None


class UserDeleted(UserNotification):
    action: Notification.Type = Notification.Type.user_deleted
    by: AdminDetails
    user: UserNotificationResponse
    reason: str | None = None


class UserLimited(UserNotification):
    action: Notification.Type = Notification.Type.user_limited
    by: AdminDetails | None = None
    user: UserNotificationResponse


class UserExpired(UserNotification):
    action: Notification.Type = Notification.Type.user_expired
    by: AdminDetails | None = None
    user: UserNotificationResponse


class UserEnabled(UserNotification):
    action: Notification.Type = Notification.Type.user_enabled
    by: AdminDetails | None = None
    user: UserNotificationResponse


class UserDisabled(UserNotification):
    action: Notification.Type = Notification.Type.user_disabled
    by: AdminDetails | None = None
    user: UserNotificationResponse
    reason: str | None = None


class UserDataUsageReset(UserNotification):
    action: Notification.Type = Notification.Type.data_usage_reset
    by: AdminDetails
    user: UserNotificationResponse
    reset_traffic: int | None = None


class UserDataResetByNext(UserNotification):
    action: Notification.Type = Notification.Type.data_reset_by_next
    by: AdminDetails | None = None
    user: UserNotificationResponse


class UserSubscriptionRevoked(UserNotification):
    action: Notification.Type = Notification.Type.subscription_revoked
    by: AdminDetails
    user: UserNotificationResponse


def status_change_message(
    user: UserNotificationResponse, by: AdminDetails | None = None, reason: str | None = None
) -> Notification | None:
    if user.status == UserStatus.limited:
        return UserLimited(username=user.username, user=user, by=by)
    if user.status == UserStatus.expired:
        return UserExpired(username=user.username, user=user, by=by)
    if user.status == UserStatus.disabled:
        return UserDisabled(username=user.username, user=user, by=by, reason=reason)
    if user.status == UserStatus.active or user.status == UserStatus.on_hold:
        return UserEnabled(username=user.username, user=user, by=by)
    return None


async def status_change(user: UserNotificationResponse, by: AdminDetails | None = None, reason: str | None = None):
    if message := status_change_message(user, by, reason):
        await notify(message)


async def notify(message: type[Notification]) -> None:
    if (await webhook_settings()).enable:
        await enqueue_webhook(jsonable_encoder(message))


async def bulk_notify(messages: list[type[Notification]]) -> None:
    if (await webhook_settings()).enable:
        for message in messages:
            await enqueue_webhook(jsonable_encoder(message))
