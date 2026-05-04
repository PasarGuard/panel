import asyncio

from app import scheduler
from app.db import GetDB
from app.db.crud.user import autodelete_expired_users
from app import notification
from app.jobs.dependencies import SYSTEM_ADMIN
from app.utils.logger import get_logger
from config import job_settings, runtime_settings, user_cleanup_settings


logger = get_logger("jobs")


async def remove_expired_users():
    async with GetDB() as db:
        deleted_users = await autodelete_expired_users(db, user_cleanup_settings.include_limited_accounts)

        for user in deleted_users:
            asyncio.create_task(notification.remove_user(user=user, by=SYSTEM_ADMIN))
            logger.info(f"User `{user.username}` has been deleted due to expiration.")


if runtime_settings.role.runs_scheduler:
    scheduler.add_job(
        remove_expired_users,
        "interval",
        coalesce=True,
        seconds=job_settings.remove_expired_users_interval,
        max_instances=1,
        id="remove_expired_users",
        replace_existing=True,
    )
