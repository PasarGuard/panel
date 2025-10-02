import asyncio
from datetime import UTC, datetime as dt, timedelta as td

from app import notification, scheduler
from app.core.manager import core_manager
from app.db import GetDB
from app.db.crud.user import bulk_reset_user_data_usage, get_users_to_reset_data_usage
from app.db.models import UserStatus
from app.jobs.dependencies import SYSTEM_ADMIN
from app.models.user import UserNotificationResponse
from app.node import node_manager
from app.utils.logger import get_logger
from config import JOB_RESET_USER_DATA_USAGE_INTERVAL

logger = get_logger("jobs")


async def reset_data_usage():
    async with GetDB() as db:
        users = await get_users_to_reset_data_usage(db)
        old_statuses = {user.id: user.status for user in users}

        updated_users = await bulk_reset_user_data_usage(db, users)

        for db_user in updated_users:
            user = UserNotificationResponse.model_validate(db_user)
            asyncio.create_task(notification.reset_user_data_usage(user, SYSTEM_ADMIN))

            if old_statuses.get(user.id) != user.status:
                asyncio.create_task(notification.user_status_change(user, SYSTEM_ADMIN))

            # make user active if limited on usage reset
            if user.status == UserStatus.active:
                asyncio.create_task(node_manager.update_user(user=user, inbounds=await core_manager.get_inbounds()))

            logger.info(f'User data usage reset for User "{user.username}"')


scheduler.add_job(
    reset_data_usage,
    "interval",
    seconds=JOB_RESET_USER_DATA_USAGE_INTERVAL,
    coalesce=True,
    start_date=dt.now(UTC) + td(minutes=1),
    max_instances=1,
)
