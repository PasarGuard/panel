from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import scheduler
from app.db import GetDB
from app.db.models import NodeStat, NodeUsage, NodeUserUsage
from app.settings import cleanup_settings
from app.utils.logger import get_logger
from config import job_settings, runtime_settings

logger = get_logger("cleanup-retention")

RETENTION_DELETE_BATCH_SIZE = 10_000
RETENTION_MAX_ROWS_PER_TABLE = 1_000_000


async def delete_expired_rows_in_batches(
    db: AsyncSession,
    model,
    cutoff: datetime,
    *,
    batch_size: int = RETENTION_DELETE_BATCH_SIZE,
    max_rows: int = RETENTION_MAX_ROWS_PER_TABLE,
) -> int:
    """Delete the oldest rows in bounded transactions without a large ``IN`` clause."""
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

        boundary_id, boundary_created_at = rows[-1]
        await db.execute(
            delete(model).where(
                model.created_at < cutoff,
                or_(
                    model.created_at < boundary_created_at,
                    and_(model.created_at == boundary_created_at, model.id <= boundary_id),
                ),
            )
        )
        await db.commit()
        deleted_total += len(rows)

        if len(rows) < current_batch_size:
            break

    return deleted_total


async def cleanup_retention_data(*, now: datetime | None = None) -> dict[str, int]:
    """Delete data older than each enabled retention policy."""
    retention = await cleanup_settings()
    now = now or datetime.now(UTC)
    deleted: dict[str, int] = {}

    targets = []
    if retention.usage_history_retention_days is not None:
        usage_cutoff = now - timedelta(days=retention.usage_history_retention_days)
        targets.extend(((NodeUserUsage, usage_cutoff), (NodeUsage, usage_cutoff)))
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

    return deleted


if runtime_settings.role.runs_scheduler:
    scheduler.add_job(
        cleanup_retention_data,
        "interval",
        seconds=job_settings.cleanup_retention_interval,
        coalesce=True,
        max_instances=1,
        id="cleanup_retention_data",
        replace_existing=True,
    )
