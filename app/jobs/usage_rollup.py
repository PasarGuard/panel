import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NodeOutboundUsage, NodeUsage, NodeUserUsage
from app.models.settings import CleanupSettings
from app.utils.logger import get_logger

logger = get_logger("usage-rollup")

# Bucket transactions per table and run; a large first run drains over several hourly runs
ROLLUP_MAX_BUCKETS_PER_TABLE = 2000
# Work per hourly run and the pause between buckets: a large first catch-up spreads over days at a low load
# instead of keeping the database busy for hours (measured on 100k users: about an hour of slower charts)
ROLLUP_MAX_SECONDS_PER_RUN = 120
ROLLUP_PAUSE_SECONDS = 0.2
# Rows this recent are never merged: the PostgreSQL user usage buffer and late flushes stay far below it
ROLLUP_MIN_AGE = timedelta(days=1)

HOUR = timedelta(hours=1)
HALF_DAY = timedelta(hours=12)
DAY = timedelta(days=1)
LEVELS = (HOUR, HALF_DAY, DAY)

# model, key columns, summed columns; the small tables first, so the large user table cannot use up their time
ROLLUP_TABLES = (
    (NodeUsage, ("node_id",), ("uplink", "downlink")),
    (NodeOutboundUsage, ("node_id", "outbound_tag"), ("uplink", "downlink")),
    (NodeUserUsage, ("user_id", "node_id"), ("used_traffic",)),
)


@dataclass
class RollupResult:
    rows_before: int = 0
    rows_after: int = 0
    buckets: int = 0
    budget_reached: bool = False


def _as_utc(value: datetime) -> datetime:
    """MySQL and SQLite return naive UTC, PostgreSQL returns the session time zone."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _day_start(value: datetime, tz: tzinfo) -> datetime:
    local = value.astimezone(tz)
    return datetime(local.year, local.month, local.day, tzinfo=tz)


def bucket_bounds(value: datetime, step: timedelta, tz: tzinfo = UTC) -> tuple[datetime, datetime]:
    """Return the UTC start and end of the bucket holding ``value``, cut on wall-clock boundaries of ``tz``."""
    local = value.astimezone(tz)
    if step == HOUR:
        start = datetime(local.year, local.month, local.day, local.hour, tzinfo=tz)
    elif step == HALF_DAY:
        start = datetime(local.year, local.month, local.day, 12 if local.hour >= 12 else 0, tzinfo=tz)
    elif step == DAY:
        start = datetime(local.year, local.month, local.day, tzinfo=tz)
    else:
        raise ValueError(f"Unsupported rollup step {step}")
    # Aware arithmetic on a zone-attached datetime is wall-clock arithmetic
    return start.astimezone(UTC), (start + step).astimezone(UTC)


def rollup_levels(cleanup: CleanupSettings) -> list[tuple[timedelta, int]]:
    """Return the enabled (step, days) pairs, finest first."""
    configured = (
        (HOUR, cleanup.usage_rollup_hourly_after_days),
        (HALF_DAY, cleanup.usage_rollup_half_day_after_days),
        (DAY, cleanup.usage_rollup_daily_after_days),
    )
    return [(step, days) for step, days in configured if days is not None]


def _target_step(day_end: datetime, now: datetime, levels: list[tuple[timedelta, int]]) -> timedelta | None:
    """Coarsest enabled step whose cutoff the whole day is older than."""
    for step, days in reversed(levels):
        if day_end <= now - timedelta(days=days):
            return step
    return None


async def _merge_bucket(db: AsyncSession, model, keys, values, start: datetime, end: datetime) -> tuple[int, int]:
    """Replace every row of one bucket with one summed row per key, in one transaction."""
    created_at = model.created_at
    in_bucket = (created_at >= start, created_at < end)
    key_columns = [getattr(model, key) for key in keys]
    rows = (
        await db.execute(
            select(*key_columns, *(func.sum(getattr(model, value)) for value in values))
            .where(*in_bucket)
            .group_by(*key_columns)
        )
    ).all()
    deleted = (await db.execute(delete(model).where(*in_bucket))).rowcount
    if rows:
        await db.execute(
            insert(model),
            [
                {
                    "created_at": start,
                    **dict(zip(keys, row[: len(keys)])),
                    **{value: int(total or 0) for value, total in zip(values, row[len(keys) :])},
                }
                for row in rows
            ],
        )
    await db.commit()
    return deleted, len(rows)


async def rollup_table(
    db: AsyncSession,
    model,
    keys: tuple[str, ...],
    values: tuple[str, ...],
    levels: list[tuple[timedelta, int]],
    now: datetime,
    *,
    tz: tzinfo = UTC,
    max_buckets: int = ROLLUP_MAX_BUCKETS_PER_TABLE,
    deadline: float | None = None,
    pause: float = 0,
) -> RollupResult:
    """Merge one table's old rows into the coarsest enabled bucket of each whole day."""
    result = RollupResult()
    if not levels:
        return result

    cutoff = now - timedelta(days=min(days for _, days in levels))
    if cutoff > now - ROLLUP_MIN_AGE:
        raise RuntimeError("Usage rollup must not touch rows newer than one day")

    timestamps = (
        await db.execute(
            select(model.created_at, func.count()).where(model.created_at < cutoff).group_by(model.created_at)
        )
    ).all()
    if not timestamps:
        return result

    days: dict[datetime, set[datetime]] = defaultdict(set)
    for created_at, count in timestamps:
        created_at = _as_utc(created_at)
        days[_day_start(created_at, tz)].add(created_at)
        result.rows_before += count
    result.rows_after = result.rows_before

    for day_start in sorted(days):
        # Wall-clock day end, so a DST day stays one calendar day
        day_end = datetime(day_start.year, day_start.month, day_start.day, tzinfo=tz) + DAY
        target = _target_step(day_end.astimezone(UTC), now, levels)
        if target is None:
            continue

        day_timestamps = days[day_start]
        # Cascade through the finer steps so each transaction stays small
        for step in LEVELS:
            if step > target:
                break
            buckets: dict[tuple[datetime, datetime], set[datetime]] = defaultdict(set)
            for created_at in day_timestamps:
                buckets[bucket_bounds(created_at, step, tz)].add(created_at)

            merged: set[datetime] = set()
            for (start, end), members in sorted(buckets.items()):
                if len(members) == 1 and start in members:
                    merged.add(start)
                    continue
                if result.buckets >= max_buckets or (deadline is not None and time.monotonic() >= deadline):
                    result.budget_reached = True
                    return result
                if end > now - ROLLUP_MIN_AGE:
                    raise RuntimeError("Usage rollup must not touch rows newer than one day")
                deleted, inserted = await _merge_bucket(db, model, keys, values, start, end)
                result.buckets += 1
                result.rows_after += inserted - deleted
                merged.add(start)
                if pause:
                    # Leave the database to the panel's own queries between buckets
                    await asyncio.sleep(pause)
            day_timestamps = merged

    return result


async def rollup_usage_history(
    db: AsyncSession,
    cleanup: CleanupSettings,
    now: datetime,
    *,
    tz: tzinfo = UTC,
    max_buckets: int = ROLLUP_MAX_BUCKETS_PER_TABLE,
    max_seconds: float | None = None,
    pause: float = 0,
) -> dict[str, RollupResult]:
    """Merge old usage rows into coarser buckets for every enabled rollup step. Totals stay exact.

    ``max_seconds`` bounds the work of one call across all tables; the rest continues on the next call."""
    levels = rollup_levels(cleanup)
    results: dict[str, RollupResult] = {}
    if not levels:
        return results
    deadline = time.monotonic() + max_seconds if max_seconds is not None else None

    for model, keys, values in ROLLUP_TABLES:
        result = await rollup_table(
            db, model, keys, values, levels, now, tz=tz, max_buckets=max_buckets, deadline=deadline, pause=pause
        )
        results[model.__tablename__] = result
        if result.buckets:
            logger.info(
                "Rolled up %s: %s rows -> %s rows in %s buckets%s",
                model.__tablename__,
                result.rows_before,
                result.rows_after,
                result.buckets,
                "; the rest continues next run" if result.budget_reached else "",
            )

    return results
