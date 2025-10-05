from sqlalchemy import func, select, delete

from app import scheduler
from app.db import GetDB
from app.db.base import DATABASE_DIALECT
from app.db.models import UserSubscriptionUpdate
from app.utils.logger import get_logger
from config import USER_SUBSCRIPTION_CLIENTS_LIMIT, JOB_CLEANUP_SUBSCRIPTION_UPDATES_INTERVAL

logger = get_logger("jobs")


async def cleanup_user_subscription_updates():
    """Clean up excess user subscription updates."""

    async with GetDB() as db:
        # First query: Find users that have more than the limit
        users_with_excess = await db.execute(
            select(UserSubscriptionUpdate.user_id)
            .group_by(UserSubscriptionUpdate.user_id)
            .having(func.count(UserSubscriptionUpdate.id) > USER_SUBSCRIPTION_CLIENTS_LIMIT)
        )
        user_ids = [row.user_id for row in users_with_excess]

        if not user_ids:
            logger.info("No users with excess subscription updates")
            return

        # Second query: Use different approaches based on database type
        if DATABASE_DIALECT == "mysql":
            # MySQL/MariaDB: Use correlated subquery without LIMIT
            total_deleted = 0
            for user_id in user_ids:
                # Get IDs to keep (most recent N records)
                keep_ids_result = await db.execute(
                    select(UserSubscriptionUpdate.id)
                    .where(UserSubscriptionUpdate.user_id == user_id)
                    .order_by(UserSubscriptionUpdate.created_at.desc())
                    .limit(USER_SUBSCRIPTION_CLIENTS_LIMIT)
                )
                keep_ids = [row.id for row in keep_ids_result]

                if keep_ids:
                    # Delete records not in keep list
                    result = await db.execute(
                        delete(UserSubscriptionUpdate).where(
                            UserSubscriptionUpdate.user_id == user_id, UserSubscriptionUpdate.id.notin_(keep_ids)
                        )
                    )
                    total_deleted += result.rowcount

            logger.info(f"Cleaned up {total_deleted} old subscription updates")
        else:
            # SQLite and PostgreSQL: Use original approach with LIMIT in subquery
            sub = UserSubscriptionUpdate.__table__.alias("sub")

            keep_subquery = (
                select(sub.c.id)
                .where(sub.c.user_id == UserSubscriptionUpdate.user_id)
                .order_by(sub.c.created_at.desc())
                .limit(USER_SUBSCRIPTION_CLIENTS_LIMIT)
            )

            result = await db.execute(
                delete(UserSubscriptionUpdate).where(
                    UserSubscriptionUpdate.user_id.in_(user_ids), UserSubscriptionUpdate.id.notin_(keep_subquery)
                )
            )
            logger.info(f"Cleaned up {result.rowcount} old subscription updates")

        await db.commit()


if USER_SUBSCRIPTION_CLIENTS_LIMIT and USER_SUBSCRIPTION_CLIENTS_LIMIT >= 0:
    # Schedule the cleanup job to run every few minutes
    scheduler.add_job(
        cleanup_user_subscription_updates,
        "interval",
        seconds=JOB_CLEANUP_SUBSCRIPTION_UPDATES_INTERVAL,
        max_instances=1,
    )
