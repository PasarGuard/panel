import asyncio

from app import notification, scheduler
from app.db import GetDB
from app.db.crud.user import get_autodelete_expired_users_batch, remove_users
from app.jobs.dependencies import SYSTEM_ADMIN
from app.node.sync import finalize_users_removal, remove_users_and_wait, resolve_user_removal_after_db_error
from app.utils.logger import get_logger
from config import job_settings, runtime_settings, user_cleanup_settings

logger = get_logger("jobs")
EXPIRED_USER_DELETE_BATCH_SIZE = 100


async def remove_expired_users():
    async with GetDB() as db:
        after_id = 0
        while True:
            db_users, deleted_users, next_after_id = await get_autodelete_expired_users_batch(
                db,
                user_cleanup_settings.include_limited_accounts,
                after_id=after_id,
                scan_limit=EXPIRED_USER_DELETE_BATCH_SIZE,
            )
            if next_after_id is None:
                break
            if db_users:
                revocation = await remove_users_and_wait(db_users)
                try:
                    await remove_users(db, db_users)
                except BaseException:
                    await resolve_user_removal_after_db_error(revocation, db)
                    raise
                if revocation is not None:
                    await finalize_users_removal(revocation)
                for user in deleted_users:
                    asyncio.create_task(notification.remove_user(user=user, by=SYSTEM_ADMIN))
                    logger.info(f"User `{user.username}` has been deleted due to expiration.")
            after_id = next_after_id


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
