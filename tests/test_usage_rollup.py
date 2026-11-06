import importlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.models import NodeOutboundUsage, NodeUsage, NodeUserUsage
from app.jobs.usage_rollup import DAY, HALF_DAY, HOUR, bucket_bounds, rollup_usage_history
from app.models.settings import CleanupSettings, SettingsSchema

cleanup_retention_job = importlib.import_module("app.jobs.cleanup_retention")
usage_rollup = importlib.import_module("app.jobs.usage_rollup")

NOW = datetime(2026, 10, 30, 12, 5, tzinfo=UTC)
# A whole UTC day, 40 days before NOW
OLD_DAY = datetime(2026, 9, 20, tzinfo=UTC)


@pytest.fixture
async def rollup_db():
    """Provide an isolated in-memory database for rollup tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _seed_day(db, day: datetime, *, step: timedelta = timedelta(minutes=10)):
    """Write one 10-minute row per key for a whole day, with NULL node ids included."""
    created_at = day
    index = 0
    while created_at < day + DAY:
        db.add_all(
            [
                NodeUserUsage(created_at=created_at, user_id=1, node_id=1, used_traffic=index + 1),
                NodeUserUsage(created_at=created_at, user_id=1, node_id=None, used_traffic=2),
                NodeUserUsage(created_at=created_at, user_id=2, node_id=1, used_traffic=3),
                NodeUsage(created_at=created_at, node_id=1, uplink=index, downlink=1),
                NodeUsage(created_at=created_at, node_id=None, uplink=5, downlink=7),
                NodeOutboundUsage(created_at=created_at, node_id=1, outbound_tag="direct", uplink=1, downlink=index),
                NodeOutboundUsage(created_at=created_at, node_id=1, outbound_tag="Direct", uplink=2, downlink=2),
            ]
        )
        created_at += step
        index += 1
    await db.commit()


async def _totals(db):
    """Sum every value per key, ignoring timestamps."""
    return {
        "user": sorted(
            (
                await db.execute(
                    select(NodeUserUsage.user_id, NodeUserUsage.node_id, func.sum(NodeUserUsage.used_traffic)).group_by(
                        NodeUserUsage.user_id, NodeUserUsage.node_id
                    )
                )
            ).all(),
            key=repr,
        ),
        "node": sorted(
            (
                await db.execute(
                    select(NodeUsage.node_id, func.sum(NodeUsage.uplink), func.sum(NodeUsage.downlink)).group_by(
                        NodeUsage.node_id
                    )
                )
            ).all(),
            key=repr,
        ),
        "outbound": sorted(
            (
                await db.execute(
                    select(
                        NodeOutboundUsage.node_id,
                        NodeOutboundUsage.outbound_tag,
                        func.sum(NodeOutboundUsage.uplink),
                        func.sum(NodeOutboundUsage.downlink),
                    ).group_by(NodeOutboundUsage.node_id, NodeOutboundUsage.outbound_tag)
                )
            ).all(),
            key=repr,
        ),
    }


async def _timestamps(db, model):
    return sorted({_utc(value) for value in (await db.scalars(select(model.created_at))).all()})


async def _count(db, model):
    return await db.scalar(select(func.count()).select_from(model))


@pytest.mark.parametrize(
    ("days_after", "step", "rows"),
    [
        ({"usage_rollup_hourly_after_days": 30}, HOUR, 24),
        ({"usage_rollup_half_day_after_days": 30}, HALF_DAY, 2),
        ({"usage_rollup_daily_after_days": 30}, DAY, 1),
        (
            {
                "usage_rollup_hourly_after_days": 2,
                "usage_rollup_half_day_after_days": 10,
                "usage_rollup_daily_after_days": 30,
            },
            DAY,
            1,
        ),
    ],
)
@pytest.mark.asyncio
async def test_rollup_keeps_totals_and_reaches_target_step(rollup_db, days_after, step, rows):
    await _seed_day(rollup_db, OLD_DAY)
    before = await _totals(rollup_db)

    results = await rollup_usage_history(rollup_db, CleanupSettings(**days_after), NOW)

    assert await _totals(rollup_db) == before
    expected = [OLD_DAY + step * index for index in range(rows)]
    for model in (NodeUserUsage, NodeUsage, NodeOutboundUsage):
        assert await _timestamps(rollup_db, model) == expected
    # Three user keys (one with a NULL node), two node keys (one NULL), two case-sensitive outbound tags
    assert await _count(rollup_db, NodeUserUsage) == rows * 3
    assert await _count(rollup_db, NodeUsage) == rows * 2
    assert await _count(rollup_db, NodeOutboundUsage) == rows * 2
    assert results["node_user_usages"].rows_before == 144 * 3
    assert results["node_user_usages"].rows_after == rows * 3


@pytest.mark.asyncio
async def test_rollup_cascades_through_finer_steps(rollup_db):
    """A daily target is reached through hourly and 12-hour merges: 24 + 2 + 1 buckets."""
    await _seed_day(rollup_db, OLD_DAY)

    results = await rollup_usage_history(rollup_db, CleanupSettings(usage_rollup_daily_after_days=30), NOW)

    assert results["node_usages"].buckets == 27


@pytest.mark.asyncio
async def test_rollup_picks_step_by_day_age(rollup_db):
    """Each day gets the coarsest step whose cutoff the whole day has passed."""
    hourly_day = NOW.replace(hour=0, minute=0) - timedelta(days=5)
    half_day_day = NOW.replace(hour=0, minute=0) - timedelta(days=15)
    for day in (hourly_day, half_day_day, OLD_DAY):
        await _seed_day(rollup_db, day, step=timedelta(minutes=30))
    before = await _totals(rollup_db)

    await rollup_usage_history(
        rollup_db,
        CleanupSettings(
            usage_rollup_hourly_after_days=3,
            usage_rollup_half_day_after_days=10,
            usage_rollup_daily_after_days=30,
        ),
        NOW,
    )

    assert await _totals(rollup_db) == before
    assert await _timestamps(rollup_db, NodeUsage) == (
        [OLD_DAY] + [half_day_day, half_day_day + HALF_DAY] + [hourly_day + HOUR * index for index in range(24)]
    )


@pytest.mark.asyncio
async def test_rollup_disabled_leaves_data_untouched(rollup_db):
    await _seed_day(rollup_db, OLD_DAY)

    assert await rollup_usage_history(rollup_db, CleanupSettings(), NOW) == {}
    assert await _count(rollup_db, NodeUserUsage) == 144 * 3


@pytest.mark.asyncio
async def test_rollup_is_idempotent(rollup_db):
    await _seed_day(rollup_db, OLD_DAY)
    settings = CleanupSettings(usage_rollup_hourly_after_days=2, usage_rollup_daily_after_days=30)
    await rollup_usage_history(rollup_db, settings, NOW)
    totals = await _totals(rollup_db)
    rows = (await rollup_db.execute(select(NodeOutboundUsage.id, NodeOutboundUsage.uplink))).all()

    results = await rollup_usage_history(rollup_db, settings, NOW)

    assert all(result.buckets == 0 for result in results.values())
    assert await _totals(rollup_db) == totals
    assert (await rollup_db.execute(select(NodeOutboundUsage.id, NodeOutboundUsage.uplink))).all() == rows


@pytest.mark.asyncio
async def test_rollup_resumes_after_budget_cut(rollup_db):
    await _seed_day(rollup_db, OLD_DAY)
    before = await _totals(rollup_db)
    settings = CleanupSettings(usage_rollup_daily_after_days=30)

    runs = 0
    while True:
        results = await rollup_usage_history(rollup_db, settings, NOW, max_buckets=5)
        runs += 1
        # Every bucket is either fully old or fully new, so totals hold after every cut run
        assert await _totals(rollup_db) == before
        if not any(result.budget_reached for result in results.values()):
            break

    # 27 buckets per table in runs of 5
    assert runs == 6
    for model in (NodeUserUsage, NodeUsage, NodeOutboundUsage):
        assert await _timestamps(rollup_db, model) == [OLD_DAY]


@pytest.mark.asyncio
async def test_rollup_stops_at_the_time_limit_and_resumes(rollup_db, monkeypatch):
    """A run stops once its time is used up; the next run continues where it stopped."""
    await _seed_day(rollup_db, OLD_DAY)
    before = await _totals(rollup_db)
    settings = CleanupSettings(usage_rollup_daily_after_days=30)

    # Each monotonic() call moves the clock 1 s: a 5 s limit allows a few buckets per run
    # (each table also takes one tick for its start check)
    clock = iter(range(100_000))
    monkeypatch.setattr(usage_rollup, "time", SimpleNamespace(monotonic=lambda: next(clock)))

    runs = 0
    while True:
        results = await rollup_usage_history(rollup_db, settings, NOW, max_seconds=5)
        runs += 1
        assert await _totals(rollup_db) == before
        if not any(result.budget_reached for result in results.values()):
            break

    assert runs > 1
    for model in (NodeUserUsage, NodeUsage, NodeOutboundUsage):
        assert await _timestamps(rollup_db, model) == [OLD_DAY]


@pytest.mark.asyncio
async def test_rollup_pauses_between_buckets(rollup_db, monkeypatch):
    await _seed_day(rollup_db, OLD_DAY)
    sleep = AsyncMock()
    monkeypatch.setattr(usage_rollup, "asyncio", SimpleNamespace(sleep=sleep))

    await rollup_usage_history(rollup_db, CleanupSettings(usage_rollup_daily_after_days=30), NOW, pause=0.2)

    # 27 buckets per table, three tables
    assert sleep.await_count == 81
    sleep.assert_awaited_with(0.2)


@pytest.mark.asyncio
async def test_rollup_leaves_recent_rows_untouched(rollup_db):
    """Rows newer than the cutoff, or in a day that is not wholly past it, are not merged."""
    yesterday = NOW.replace(hour=0, minute=0) - DAY
    await _seed_day(rollup_db, yesterday)
    await _seed_day(rollup_db, NOW.replace(hour=0, minute=0))

    results = await rollup_usage_history(rollup_db, CleanupSettings(usage_rollup_hourly_after_days=1), NOW)

    # Yesterday ends at today's midnight, which is not a whole day before NOW
    assert all(result.buckets == 0 for result in results.values())
    assert await _count(rollup_db, NodeUsage) == 2 * 144 * 2


@pytest.mark.asyncio
async def test_rollup_merges_into_existing_bucket_start_row(rollup_db):
    """A row already at the bucket start is merged with the rest of its bucket."""
    rollup_db.add_all(
        [
            NodeUsage(created_at=OLD_DAY, node_id=1, uplink=10, downlink=1),
            NodeUsage(created_at=OLD_DAY + timedelta(minutes=10), node_id=1, uplink=5, downlink=1),
            NodeUsage(created_at=OLD_DAY + timedelta(hours=13), node_id=1, uplink=1, downlink=1),
        ]
    )
    await rollup_db.commit()

    await rollup_usage_history(rollup_db, CleanupSettings(usage_rollup_daily_after_days=30), NOW)

    rows = (await rollup_db.execute(select(NodeUsage.created_at, NodeUsage.uplink, NodeUsage.downlink))).all()
    assert [(_utc(created_at), up, down) for created_at, up, down in rows] == [(OLD_DAY, 16, 3)]


@pytest.mark.asyncio
async def test_cleanup_job_runs_rollup_after_retention(rollup_db, monkeypatch):
    """Rows past retention are deleted, not rolled up first."""
    await _seed_day(rollup_db, OLD_DAY)
    await _seed_day(rollup_db, OLD_DAY - timedelta(days=30))
    db_context = MagicMock()
    db_context.__aenter__.return_value = rollup_db
    monkeypatch.setattr(
        cleanup_retention_job,
        "cleanup_settings",
        AsyncMock(return_value=CleanupSettings(usage_history_retention_days=60, usage_rollup_daily_after_days=30)),
    )
    monkeypatch.setattr(cleanup_retention_job, "GetDB", MagicMock(return_value=db_context))
    monkeypatch.setattr(cleanup_retention_job, "ROLLUP_PAUSE_SECONDS", 0)

    deleted = await cleanup_retention_job.cleanup_retention_data(now=NOW)

    assert deleted["node_usages"] == 144 * 2
    assert await _timestamps(rollup_db, NodeUsage) == [OLD_DAY]


@pytest.mark.asyncio
async def test_rollup_skips_tables_once_the_time_is_used_up(rollup_db, monkeypatch):
    """No timestamp scan starts after the deadline."""
    await _seed_day(rollup_db, OLD_DAY)
    monkeypatch.setattr(usage_rollup, "time", SimpleNamespace(monotonic=iter([0, 5, 5, 5]).__next__))
    execute = AsyncMock(wraps=rollup_db.execute)
    monkeypatch.setattr(rollup_db, "execute", execute)

    results = await rollup_usage_history(
        rollup_db, CleanupSettings(usage_rollup_daily_after_days=30), NOW, max_seconds=3
    )

    assert all(result.budget_reached and result.buckets == 0 for result in results.values())
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_retention_keeps_a_rolled_day_until_the_whole_day_is_past(rollup_db, monkeypatch):
    """With rollup on, a daily row at midnight stays while the end of its day is inside retention."""
    db_context = MagicMock()
    db_context.__aenter__.return_value = rollup_db
    monkeypatch.setattr(cleanup_retention_job, "GetDB", MagicMock(return_value=db_context))
    monkeypatch.setattr(cleanup_retention_job, "ROLLUP_PAUSE_SECONDS", 0)
    retention_day = (NOW - timedelta(days=60)).replace(hour=0, minute=0)
    rollup_db.add_all(
        [
            NodeUsage(created_at=retention_day, node_id=1, uplink=1, downlink=1),
            NodeUsage(created_at=retention_day - DAY, node_id=1, uplink=1, downlink=1),
        ]
    )
    await rollup_db.commit()

    for rollup_days, kept in ((30, [retention_day]), (None, [])):
        monkeypatch.setattr(
            cleanup_retention_job,
            "cleanup_settings",
            AsyncMock(
                return_value=CleanupSettings(usage_history_retention_days=60, usage_rollup_daily_after_days=rollup_days)
            ),
        )
        await cleanup_retention_job.cleanup_retention_data(now=NOW)
        assert await _timestamps(rollup_db, NodeUsage) == kept


def test_bucket_bounds_cut_in_utc_and_other_zones():
    value = datetime(2026, 9, 20, 13, 40, tzinfo=UTC)
    assert bucket_bounds(value, HOUR) == (datetime(2026, 9, 20, 13, tzinfo=UTC), datetime(2026, 9, 20, 14, tzinfo=UTC))
    assert bucket_bounds(value, HALF_DAY) == (
        datetime(2026, 9, 20, 12, tzinfo=UTC),
        datetime(2026, 9, 21, tzinfo=UTC),
    )
    assert bucket_bounds(value, DAY) == (datetime(2026, 9, 20, tzinfo=UTC), datetime(2026, 9, 21, tzinfo=UTC))

    from zoneinfo import ZoneInfo

    # Tehran is UTC+03:30: the local day starts at 20:30 UTC the evening before
    assert bucket_bounds(value, DAY, ZoneInfo("Asia/Tehran")) == (
        datetime(2026, 9, 19, 20, 30, tzinfo=UTC),
        datetime(2026, 9, 20, 20, 30, tzinfo=UTC),
    )


def test_rollup_settings_default_off():
    settings = CleanupSettings()
    assert settings.usage_rollup_hourly_after_days is None
    assert settings.usage_rollup_half_day_after_days is None
    assert settings.usage_rollup_daily_after_days is None


@pytest.mark.parametrize(
    "values",
    [
        {"usage_rollup_hourly_after_days": 7},
        {"usage_rollup_hourly_after_days": 7, "usage_rollup_daily_after_days": 8},
        {"usage_rollup_half_day_after_days": 30, "usage_rollup_daily_after_days": 90},
        {
            "usage_rollup_hourly_after_days": 1,
            "usage_rollup_half_day_after_days": 2,
            "usage_rollup_daily_after_days": 3,
        },
    ],
)
def test_rollup_settings_accept_increasing_order(values):
    assert CleanupSettings(**values).model_dump(include=set(values)) == values


@pytest.mark.parametrize(
    "values",
    [
        {"usage_rollup_hourly_after_days": 7, "usage_rollup_half_day_after_days": 7},
        {"usage_rollup_hourly_after_days": 30, "usage_rollup_daily_after_days": 7},
        {"usage_rollup_half_day_after_days": 30, "usage_rollup_daily_after_days": 7},
        {"usage_rollup_hourly_after_days": 0},
        {"usage_rollup_daily_after_days": 36_501},
    ],
)
def test_rollup_settings_reject_invalid_values(values):
    with pytest.raises(ValidationError):
        CleanupSettings(**values)


def test_rollup_settings_round_trip():
    cleanup = CleanupSettings(
        usage_history_retention_days=365,
        usage_rollup_hourly_after_days=7,
        usage_rollup_half_day_after_days=30,
        usage_rollup_daily_after_days=90,
    )
    restored = SettingsSchema.model_validate({"cleanup": cleanup.model_dump(mode="json")}).cleanup
    assert restored == cleanup
