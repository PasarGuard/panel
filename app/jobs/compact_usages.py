"""Replace complete, old UTC days of usage with one row per entity and day."""

from datetime import UTC, datetime, time, timedelta

from sqlalchemy import delete, func, insert, select

from app import scheduler
from app.db import GetDB
from app.db.models import NodeUsage, NodeUserUsage
from app.utils.logger import get_logger
from config import runtime_settings

logger = get_logger("jobs")
RETENTION_DAYS = 7
MAX_DAYS_PER_RUN = 14


async def _compact_one_day(db, model, day_start: datetime) -> tuple[int, int]:
    """Replace one day's rows in a single transaction, including any prior rollup.

    Including prior rollups makes a late historical write safe to compact on the
    next run. A failed insert or delete rolls the entire day back.
    """
    day_end = day_start + timedelta(days=1)
    # SQLite's older rows may omit fractional seconds while SQLAlchemy binds
    # DateTime values with .000000. Inclusive end-of-day bounds cover both.
    previous_day_end = day_start - timedelta(microseconds=1)
    last_in_day = day_end - timedelta(microseconds=1)
    if model is NodeUserUsage:
        result = await db.execute(
            select(
                model.user_id,
                model.node_id,
                func.sum(model.used_traffic),
                func.count(model.id),
            )
            .where(model.created_at > previous_day_end, model.created_at <= last_in_day)
            .group_by(model.user_id, model.node_id)
        )
        groups = result.all()
        rows = [
            {
                "created_at": day_start,
                "user_id": user_id,
                "node_id": node_id,
                "used_traffic": int(total),
                "is_daily": True,
            }
            for user_id, node_id, total, _ in groups
        ]
        source_count = sum(count for *_, count in groups)
    else:
        result = await db.execute(
            select(model.node_id, func.sum(model.uplink), func.sum(model.downlink), func.count(model.id))
            .where(model.created_at > previous_day_end, model.created_at <= last_in_day)
            .group_by(model.node_id)
        )
        groups = result.all()
        rows = [
            {
                "created_at": day_start,
                "node_id": node_id,
                "uplink": int(up),
                "downlink": int(down),
                "is_daily": True,
            }
            for node_id, up, down, _ in groups
        ]
        source_count = sum(count for *_, count in groups)

    if rows:
        await db.execute(delete(model).where(model.created_at > previous_day_end, model.created_at <= last_in_day))
        await db.execute(insert(model), rows)
    return source_count, len(rows)


async def compact_old_usages(now: datetime | None = None, max_days: int = MAX_DAYS_PER_RUN) -> None:
    """Roll up only full UTC days whose end is at least seven days old."""
    now = now or datetime.now(UTC)
    cutoff = datetime.combine((now - timedelta(days=RETENTION_DAYS)).date(), time.min, UTC)
    for model in (NodeUserUsage, NodeUsage):
        days_done = 0
        while days_done < max_days:
            async with GetDB() as db:
                oldest = await db.scalar(
                    select(func.min(model.created_at)).where(
                        model.is_daily.is_(False), model.created_at <= cutoff - timedelta(microseconds=1)
                    )
                )
                if oldest is None:
                    break
                day_start = datetime.combine(oldest.date(), time.min, UTC)
                before, after = await _compact_one_day(db, model, day_start)
                await db.commit()
                logger.info(
                    "Compacted %s UTC day %s: %s rows to %s", model.__tablename__, day_start.date(), before, after
                )
                days_done += 1


if runtime_settings.role.runs_scheduler:
    scheduler.add_job(
        compact_old_usages,
        "interval",
        seconds=3600,
        start_date=datetime.now(UTC) + timedelta(minutes=5),
        coalesce=True,
        max_instances=1,
        id="compact_old_usages",
        replace_existing=True,
    )
