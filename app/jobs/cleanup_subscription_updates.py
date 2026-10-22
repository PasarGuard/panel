from sqlalchemy import delete, func, select

from app import scheduler
from app.db import GetDB
from app.db.models import UserSubscriptionUpdate
from app.subscription.sub_update_buffer import flush_user_sub_updates
from app.utils.logger import get_logger
from config import job_settings, runtime_settings, subscription_env_settings

logger = get_logger("jobs")


async def cleanup_user_subscription_updates():
    """Clean up excess user subscription updates."""

    await flush_user_sub_updates()

    async with GetDB() as db:
        # Rank each user's updates newest first and delete everything past the limit in one statement: no list of
        # user ids (asyncpg rejects more than 32767 bind parameters) and no per-user loop. Window functions need
        # SQLite 3.25+, MySQL 8.0+ or MariaDB 10.2+. Reading from the derived table also lets MySQL delete from the
        # table the subquery reads.
        ranked = select(
            UserSubscriptionUpdate.id,
            func.row_number()
            .over(
                partition_by=UserSubscriptionUpdate.user_id,
                order_by=(UserSubscriptionUpdate.created_at.desc(), UserSubscriptionUpdate.id.desc()),
            )
            .label("rn"),
        ).subquery()
        excess_ids = select(ranked.c.id).where(ranked.c.rn > subscription_env_settings.clients_limit)
        result = await db.execute(
            delete(UserSubscriptionUpdate)
            .where(UserSubscriptionUpdate.id.in_(excess_ids))
            .execution_options(synchronize_session=False)
        )
        await db.commit()

        if result.rowcount:
            logger.info(f"Cleaned up {result.rowcount} old subscription updates")
        else:
            logger.info("No users with excess subscription updates")


if (
    subscription_env_settings.clients_limit
    and subscription_env_settings.clients_limit >= 0
    and runtime_settings.role.runs_scheduler
):
    # Schedule the cleanup job to run every few minutes
    scheduler.add_job(
        cleanup_user_subscription_updates,
        "interval",
        seconds=job_settings.cleanup_subscription_updates_interval,
        max_instances=1,
        id="cleanup_user_subscription_updates",
        replace_existing=True,
    )
