import asyncio

from app import scheduler
from app.db import GetDB
from app.db.crud.user import autodelete_expired_users
from app import notification
from app.jobs.dependencies import SYSTEM_ADMIN
from app.utils.logger import get_logger
from config import (
    USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS,
    JOB_REMOVE_EXPIRED_USERS_INTERVAL,
    RUN_SCHEDULER,
    IS_NODE_WORKER,
)


logger = get_logger("jobs")


async def remove_expired_users():
    async with GetDB() as db:
        deleted_users = await autodelete_expired_users(db, USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS)

        for user in deleted_users:
            asyncio.create_task(notification.remove_user(user=user, by=SYSTEM_ADMIN))
            logger.info(f"User `{user.username}` has been deleted due to expiration.")


if RUN_SCHEDULER and not IS_NODE_WORKER:
    scheduler.add_job(
        remove_expired_users,
        "interval",
        coalesce=True,
        seconds=JOB_REMOVE_EXPIRED_USERS_INTERVAL,
        max_instances=1,
        id="remove_expired_users",
        replace_existing=True,
    )
