from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import scheduler
from app.db import GetDB
from app.db.models import NodeOutboundUsage, NodeStat, NodeUsage, NodeUserUsage
from app.jobs.usage_rollup import (
    ROLLUP_MAX_SECONDS_PER_RUN,
    ROLLUP_PAUSE_SECONDS,
    rollup_levels,
    rollup_usage_history,
)
from app.settings import cleanup_settings
from app.utils.logger import get_logger
from config import runtime_settings

logger = get_logger("cleanup-retention")

RETENTION_DELETE_BATCH_SIZE = 10_000
RETENTION_MAX_ROWS_PER_TABLE = 1_000_000
RETENTION_INTERVAL = 3600


async def delete_expired_rows_in_batches(
    db: AsyncSession,
    model,
    cutoff: datetime,
    *,
    batch_size: int = RETENTION_DELETE_BATCH_SIZE,
    max_rows: int = RETENTION_MAX_ROWS_PER_TABLE,
) -> int:
    """Delete the oldest rows in bounded transactions by their selected IDs."""
    deleted_total = 0

    while deleted_total < max_rows:
        current_batch_size = min(batch_size, max_rows - deleted_total)
        rows = (
            await db.execute(
                select(model.id, model.created_at)
                .where(model.created_at < cutoff)
                .order_by(model.created_at, model.id)
                .limit(current_batch_size)
            )
        ).all()
        if not rows:
            break

        selected_ids = [row_id for row_id, _ in rows]
        delete_result = await db.execute(
            delete(model).where(
                model.id.in_(selected_ids),
                model.created_at < cutoff,
            )
        )
        deleted_count = delete_result.rowcount
        if deleted_count is None or deleted_count < 0:
            raise RuntimeError(f"Could not determine deleted row count for {model.__tablename__}")
        await db.commit()
        deleted_total += deleted_count

        if deleted_count < current_batch_size:
            break

    return deleted_total


async def cleanup_retention_data(*, now: datetime | None = None) -> dict[str, int]:
    """Delete data older than each enabled retention policy, then merge old usage rows into coarser buckets."""
    retention = await cleanup_settings()
    now = now or datetime.now(UTC)
    deleted: dict[str, int] = {}

    targets = []
    if retention.usage_history_retention_days is not None:
        usage_cutoff = now - timedelta(days=retention.usage_history_retention_days)
        if rollup_levels(retention):
            # A rolled row is stamped at its bucket start; keep it until its whole bucket (at most a UTC day) is past
            usage_cutoff = usage_cutoff.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        targets.extend(((NodeUserUsage, usage_cutoff), (NodeUsage, usage_cutoff), (NodeOutboundUsage, usage_cutoff)))
    if retention.node_stats_retention_days is not None:
        targets.append((NodeStat, now - timedelta(days=retention.node_stats_retention_days)))

    async with GetDB() as db:
        for model, cutoff in targets:
            count = await delete_expired_rows_in_batches(db, model, cutoff)
            deleted[model.__tablename__] = count
            if count:
                logger.info("Deleted %s expired rows from %s", count, model.__tablename__)
            if count >= RETENTION_MAX_ROWS_PER_TABLE:
                logger.warning(
                    "Retention cleanup for %s reached the per-run safety limit; remaining rows will be retried",
                    model.__tablename__,
                )

        # After the deletes, so rows about to expire are not merged first
        await rollup_usage_history(
            db, retention, now, max_seconds=ROLLUP_MAX_SECONDS_PER_RUN, pause=ROLLUP_PAUSE_SECONDS
        )

    return deleted


if runtime_settings.role.runs_scheduler:
    scheduler.add_job(
        cleanup_retention_data,
        "interval",
        seconds=RETENTION_INTERVAL,
        coalesce=True,
        max_instances=1,
        id="cleanup_retention_data",
        replace_existing=True,
    )
