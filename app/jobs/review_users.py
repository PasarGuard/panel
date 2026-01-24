import asyncio
from datetime import datetime as dt, timedelta as td, timezone as tz

from sqlalchemy.ext.asyncio import AsyncSession

from app import notification, scheduler
from app.db import GetDB
from app.db.models import User, UserStatus, ReminderType
from app.db.crud.user import (
    get_active_to_expire_users,
    get_active_to_limited_users,
    get_days_left_reached_users,
    get_on_hold_to_active_users,
    get_usage_percentage_reached_users,
    get_users_with_ip_limit,
    reset_user_by_next,
    start_users_expire,
    update_users_status,
    bulk_create_notification_reminders,
)
from app.operation import OperatorType
from app.operation.node import NodeOperation
from app.operation.user import UserOperation
from app.jobs.dependencies import SYSTEM_ADMIN
from app.models.settings import Webhook
from app.models.user import UserNotificationResponse
from app.node import node_manager as node_manager
from app.settings import webhook_settings
from app.utils.logger import get_logger
from config import JOB_REVIEW_USERS_INTERVAL

logger = get_logger("review-users")
user_operator = UserOperation(operator_type=OperatorType.SYSTEM)
node_operator = NodeOperation(operator_type=OperatorType.SYSTEM)


async def reset_user_by_next_report(db: AsyncSession, db_user: User):
    db_user = await reset_user_by_next(db, db_user)
    user = await user_operator.update_user(db_user)

    asyncio.create_task(notification.user_data_reset_by_next(user, SYSTEM_ADMIN))

    logger.info(f'User "{db_user.username}" next plan activated')


async def change_status(db: AsyncSession, db_user: User, status: UserStatus):
    user = await user_operator.update_user(db_user)
    asyncio.create_task(notification.user_status_change(user, SYSTEM_ADMIN))

    logger.info(f'User "{user.username}" status changed to {status.value}')

    if db_user.next_plan and db_user.status != UserStatus.active:
        await reset_user_by_next_report(db, db_user)


async def expire_users_job():
    async with GetDB() as db:
        if expired_users := await get_active_to_expire_users(db):
            updated_users = await update_users_status(db, expired_users, UserStatus.expired)
            for user in updated_users:
                await change_status(db, user, UserStatus.expired)


async def limit_users_job():
    async with GetDB() as db:
        if limited_users := await get_active_to_limited_users(db):
            updated_users = await update_users_status(db, limited_users, UserStatus.limited)
            for user in updated_users:
                await change_status(db, user, UserStatus.limited)


async def ip_limit_users_job():
    """Check users' connection counts against their ip_limit and enforce."""
    async with GetDB() as db:
        users_with_limit = await get_users_with_ip_limit(db)
        if not users_with_limit:
            return

        for db_user in users_with_limit:
            try:
                ip_data = await node_operator.get_user_ip_list_all_nodes(db=db, username=db_user.username)
            except Exception as e:
                logger.warning(f'Failed to get IP data for user "{db_user.username}": {e}')
                continue

            total_connections = sum(
                sum(node_ips.ips.values())
                for node_ips in (ip_data.nodes or {}).values()
                if node_ips and node_ips.ips
            ) if ip_data else 0

            if total_connections > db_user.ip_limit and db_user.status == UserStatus.active:
                updated = await update_users_status(db, [db_user], UserStatus.limited)
                for user in updated:
                    await change_status(db, user, UserStatus.limited)
                logger.info(
                    f'User "{db_user.username}" ip-limited: {total_connections}/{db_user.ip_limit} connections'
                )
            elif total_connections <= db_user.ip_limit and db_user.status == UserStatus.limited:
                if db_user.is_data_reached:
                    continue
                updated = await update_users_status(db, [db_user], UserStatus.active)
                for user in updated:
                    await change_status(db, user, UserStatus.active)
                logger.info(
                    f'User "{db_user.username}" ip-limit lifted: {total_connections}/{db_user.ip_limit} connections'
                )


async def on_hold_to_active_users_job():
    async with GetDB() as db:
        if on_hold_users := await get_on_hold_to_active_users(db):
            updated_users = await start_users_expire(db, on_hold_users)
            for user in updated_users:
                await change_status(db, user, UserStatus.active)


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


now = dt.now(tz.utc)
interval = int(JOB_REVIEW_USERS_INTERVAL / 6)

# Register each job separately
scheduler.add_job(
    expire_users_job, "interval", seconds=JOB_REVIEW_USERS_INTERVAL, coalesce=True, max_instances=1, start_date=now
)
scheduler.add_job(
    limit_users_job,
    "interval",
    seconds=JOB_REVIEW_USERS_INTERVAL,
    coalesce=True,
    max_instances=1,
    start_date=now + td(seconds=interval),
)
scheduler.add_job(
    on_hold_to_active_users_job,
    "interval",
    seconds=JOB_REVIEW_USERS_INTERVAL,
    coalesce=True,
    max_instances=1,
    start_date=now + td(seconds=interval * 2),
)
scheduler.add_job(
    usage_percent_notification_job,
    "interval",
    seconds=JOB_REVIEW_USERS_INTERVAL,
    coalesce=True,
    max_instances=1,
    start_date=now + td(seconds=interval * 3),
)
scheduler.add_job(
    days_left_notification_job,
    "interval",
    seconds=JOB_REVIEW_USERS_INTERVAL,
    coalesce=True,
    max_instances=1,
    start_date=now + td(seconds=interval * 4),
)
scheduler.add_job(
    ip_limit_users_job,
    "interval",
    seconds=JOB_REVIEW_USERS_INTERVAL,
    coalesce=True,
    max_instances=1,
    start_date=now + td(seconds=interval * 5),
)
