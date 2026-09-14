import asyncio
from datetime import UTC, datetime as dt, timedelta as td

from sqlalchemy.ext.asyncio import AsyncSession

from app import notification, scheduler
from app.db import GetDB
from app.db.crud.user import (
    bulk_create_notification_reminders,
    get_active_to_expire_users,
    get_active_to_limited_users,
    get_days_left_reached_users,
    get_on_hold_to_active_users,
    get_usage_percentage_reached_users,
    reset_user_by_next,
    start_users_expire,
    update_users_status,
)
from app.db.models import ReminderType, User, UserStatus
from app.jobs.dependencies import SYSTEM_ADMIN
from app.models.settings import Webhook
from app.models.user import UserNotificationResponse
from app.node.sync import sync_users
from app.operation import OperatorType
from app.operation.user import UserOperation
from app.settings import webhook_settings
from app.utils.logger import get_logger
from config import job_settings, runtime_settings, usage_settings

logger = get_logger("review-users")
user_operator = UserOperation(operator_type=OperatorType.SYSTEM)


async def _notify_status_change(db_user: User, status: UserStatus) -> None:
    user = await user_operator.validate_user(db_user)
    asyncio.create_task(notification.user_status_change(user, SYSTEM_ADMIN))
    logger.info(f'User "{user.username}" status changed to {status.value}')


async def _notify_next_plan(db_user: User) -> None:
    user = await user_operator.validate_user(db_user)
    asyncio.create_task(notification.user_data_reset_by_next(user, SYSTEM_ADMIN))
    logger.info(f'User "{db_user.username}" next plan activated')


async def apply_status_changes(db: AsyncSession, users: list[User], status: UserStatus) -> None:
    """Bulk-sync status changes, only walking next-plan users one by one."""
    if not users:
        return

    next_plan_users: list[User] = []
    plain_users: list[User] = []
    for user in users:
        if user.next_plan is not None and status != UserStatus.active:
            next_plan_users.append(user)
        else:
            plain_users.append(user)

    if plain_users:
        if status in (UserStatus.expired, UserStatus.limited):
            await update_users_status(db, plain_users, status)
        await sync_users(plain_users)
        for db_user in plain_users:
            await _notify_status_change(db_user, status)

    if not next_plan_users:
        return

    reset_users: list[User] = []
    for db_user in next_plan_users:
        reset_users.append(
            await reset_user_by_next(
                db,
                db_user,
                clean_chart_data=usage_settings.reset_user_usage_clean_chart_data,
            )
        )
    await sync_users(reset_users)
    for db_user in reset_users:
        await _notify_next_plan(db_user)


async def expire_users_job():
    async with GetDB() as db:
        if expired_users := await get_active_to_expire_users(db):
            await apply_status_changes(db, expired_users, UserStatus.expired)


async def limit_users_job():
    async with GetDB() as db:
        if limited_users := await get_active_to_limited_users(db):
            await apply_status_changes(db, limited_users, UserStatus.limited)


async def on_hold_to_active_users_job():
    async with GetDB() as db:
        if on_hold_users := await get_on_hold_to_active_users(db):
            updated_users = await start_users_expire(db, on_hold_users)
            await apply_status_changes(db, updated_users, UserStatus.active)


async def usage_percent_notification_job():
    settings: Webhook = await webhook_settings()
    if not settings.enable:
        return
    async with GetDB() as db:
        for percent in settings.usage_percent:
            users = await get_usage_percentage_reached_users(db, percent)

            # Prepare webhook notifications first
            webhook_data = []
            reminder_data = []

            for user in users:
                usage_percentage = user.usage_percentage
                user_model = UserNotificationResponse.model_validate(user)

                # Queue webhook notification
                webhook_data.append(
                    notification.wh.ReachedUsagePercent(
                        username=user_model.username, user=user_model, used_percent=usage_percentage
                    )
                )

                # Prepare reminder data for bulk insert
                reminder_data.append(
                    {
                        "user_id": user.id,
                        "type": ReminderType.data_usage,
                        "threshold": percent,
                        "expires_at": user.expire if user.expire else None,
                    }
                )

            # Bulk create notification reminders
            if reminder_data:
                await bulk_create_notification_reminders(db, reminder_data)

            if webhook_data:
                await notification.wh.bulk_notify(webhook_data)


async def days_left_notification_job():
    settings: Webhook = await webhook_settings()
    if not settings.enable:
        return
    async with GetDB() as db:
        for days in settings.days_left:
            users = await get_days_left_reached_users(db, days)

            # Prepare webhook notifications first
            webhook_data = []
            reminder_data = []

            for user in users:
                days_left = user.days_left
                user_model = UserNotificationResponse.model_validate(user)

                # Queue webhook notification
                webhook_data.append(
                    notification.wh.ReachedDaysLeft(username=user_model.username, user=user_model, days_left=days_left)
                )

                # Prepare reminder data for bulk insert
                reminder_data.append(
                    {
                        "user_id": user.id,
                        "type": ReminderType.expiration_date,
                        "threshold": days,
                        "expires_at": user.expire,
                    }
                )
            # Bulk create notification reminders
            if reminder_data:
                await bulk_create_notification_reminders(db, reminder_data)

            if webhook_data:
                await notification.wh.bulk_notify(webhook_data)


if runtime_settings.role.runs_scheduler:
    now = dt.now(UTC)
    interval = int(job_settings.review_users_interval / 5)

    # Register each job separately
    scheduler.add_job(
        expire_users_job,
        "interval",
        seconds=job_settings.review_users_interval,
        coalesce=True,
        max_instances=1,
        start_date=now,
        id="expire_users",
        replace_existing=True,
    )
    scheduler.add_job(
        limit_users_job,
        "interval",
        seconds=job_settings.review_users_interval,
        coalesce=True,
        max_instances=1,
        start_date=now + td(seconds=interval),
        id="limit_users",
        replace_existing=True,
    )
    scheduler.add_job(
        on_hold_to_active_users_job,
        "interval",
        seconds=job_settings.review_users_interval,
        coalesce=True,
        max_instances=1,
        start_date=now + td(seconds=interval * 2),
        id="on_hold_to_active_users",
        replace_existing=True,
    )
    scheduler.add_job(
        usage_percent_notification_job,
        "interval",
        seconds=job_settings.review_users_interval,
        coalesce=True,
        max_instances=1,
        start_date=now + td(seconds=interval * 3),
        id="usage_percent_notification",
        replace_existing=True,
    )
    scheduler.add_job(
        days_left_notification_job,
        "interval",
        seconds=job_settings.review_users_interval,
        coalesce=True,
        max_instances=1,
        start_date=now + td(seconds=interval * 4),
        id="days_left_notification",
        replace_existing=True,
    )
