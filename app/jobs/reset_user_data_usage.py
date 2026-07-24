import asyncio
from datetime import UTC, datetime as dt, timedelta as td

from app import notification, scheduler
from app.db import GetDB
from app.db.crud.user import bulk_reset_user_data_usage, get_users_to_reset_data_usage
from app.jobs.dependencies import SYSTEM_ADMIN
from app.operation import OperatorType
from app.operation.user import UserOperation
from app.utils.logger import get_logger
from config import job_settings, runtime_settings, usage_settings

logger = get_logger("jobs")
user_operator = UserOperation(operator_type=OperatorType.SYSTEM)


async def reset_data_usage():
    async with GetDB() as db:
        users = await get_users_to_reset_data_usage(db)
        old_statuses = {user.id: user.status for user in users}

        updated_users = await bulk_reset_user_data_usage(
            db,
            users,
            clean_chart_data=usage_settings.reset_user_usage_clean_chart_data,
        )

        for db_user in updated_users:
            user = await user_operator.update_user(db_user)
            asyncio.create_task(notification.reset_user_data_usage(user, SYSTEM_ADMIN))

            if old_statuses.get(user.id) != user.status:
                asyncio.create_task(notification.user_status_change(user, SYSTEM_ADMIN))

            logger.info(f'User data usage reset for User "{user.username}"')


if runtime_settings.role.runs_scheduler:
    scheduler.add_job(
        reset_data_usage,
        "interval",
        seconds=job_settings.reset_user_data_usage_interval,
        coalesce=True,
        start_date=dt.now(UTC) + td(minutes=1),
        max_instances=1,
        id="reset_user_data_usage",
        replace_existing=True,
    )
