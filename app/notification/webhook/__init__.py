from datetime import datetime as dt, timezone as tz
from enum import Enum
from typing import Type
import asyncio

from pydantic import BaseModel, Field

from app.settings import webhook_settings
from app.models.admin import AdminDetails
from app.models.user import UserNotificationResponse, UserStatus

queue = asyncio.Queue()


def get_current_timestamp() -> float:
    """Factory function to get current timestamp"""
    return dt.now(tz.utc).timestamp()


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


class UserDeleted(UserNotification):
    action: Notification.Type = Notification.Type.user_deleted
    by: AdminDetails


class UserLimited(UserNotification):
    action: Notification.Type = Notification.Type.user_limited
    user: UserNotificationResponse


class UserExpired(UserNotification):
    action: Notification.Type = Notification.Type.user_expired
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


class UserDataResetByNext(UserNotification):
    action: Notification.Type = Notification.Type.data_usage_reset
    user: UserNotificationResponse


class UserSubscriptionRevoked(UserNotification):
    action: Notification.Type = Notification.Type.subscription_revoked
    by: AdminDetails
    user: UserNotificationResponse


async def status_change(user: UserNotificationResponse):
    if user.status == UserStatus.limited:
        await notify(UserLimited(username=user.username, user=user))
    elif user.status == UserStatus.expired:
        await notify(UserExpired(username=user.username, user=user))
    elif user.status == UserStatus.disabled:
        await notify(UserDisabled(username=user.username, user=user))
    elif user.status == UserStatus.active:
        await notify(UserEnabled(username=user.username, user=user))
    elif user.status == UserStatus.on_hold:
        await notify(UserEnabled(username=user.username, user=user))


async def notify(message: Type[Notification]) -> None:
    if (await webhook_settings()).enable:
        await queue.put(message)


async def bulk_notify(messages: list[Type[Notification]]) -> None:
    if (await webhook_settings()).enable:
        for message in messages:
            await queue.put(message)
