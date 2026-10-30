import asyncio

from app import notification, scheduler
from app.db import GetDB
from app.db.crud.user import AUTODELETE_MAX_USERS_PER_RUN, autodelete_expired_users
from app.jobs.dependencies import SYSTEM_ADMIN
from app.settings import cleanup_settings
from app.utils.logger import get_logger
from config import job_settings, runtime_settings

logger = get_logger("jobs")


async def remove_expired_users():
    """Remove expired users according to the global or per-user policy."""
    retention = await cleanup_settings()
    async with GetDB() as db:
        deleted_users = await autodelete_expired_users(
            db,
            retention.include_limited_users,
            default_autodelete_days=retention.expired_users_retention_days,
        )

        for user in deleted_users:
            asyncio.create_task(notification.remove_user(user=user, by=SYSTEM_ADMIN))
            logger.info(f"User `{user.username}` has been deleted due to expiration.")

        if len(deleted_users) == AUTODELETE_MAX_USERS_PER_RUN:
            logger.warning(
                "Expired-user cleanup reached its per-run limit; remaining users will be handled by a later run."
            )


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
