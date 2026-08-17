from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.models import NodeStat
from app.jobs.cleanup_retention import delete_expired_rows_in_batches
from app.models.settings import CleanupSettings
from config import JobSettings


@pytest.fixture
async def retention_db():
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


def _node_stat(node_id: int, created_at: datetime) -> NodeStat:
    stat = NodeStat(
        node_id=node_id,
        mem_total=4096,
        mem_used=1024,
        cpu_cores=4,
        cpu_usage=25,
        incoming_bandwidth_speed=10,
        outgoing_bandwidth_speed=20,
    )
    stat.created_at = created_at
    return stat


@pytest.mark.asyncio
async def test_retention_delete_is_batched_and_preserves_recent_rows(retention_db):
    now = datetime.now(UTC)
    old_timestamp = now - timedelta(days=31)
    retention_db.add_all(
        [
            _node_stat(1, old_timestamp),
            _node_stat(2, old_timestamp),
            _node_stat(3, old_timestamp),
            _node_stat(1, now - timedelta(days=29)),
        ]
    )
    await retention_db.commit()

    deleted = await delete_expired_rows_in_batches(
        retention_db,
        NodeStat,
        now - timedelta(days=30),
        batch_size=2,
        max_rows=10,
    )

    assert deleted == 3
    remaining = await retention_db.scalar(select(func.count()).select_from(NodeStat))
    assert remaining == 1


@pytest.mark.asyncio
async def test_retention_delete_honors_per_run_limit(retention_db):
    now = datetime.now(UTC)
    retention_db.add_all([_node_stat(index, now - timedelta(days=60)) for index in range(1, 6)])
    await retention_db.commit()

    deleted = await delete_expired_rows_in_batches(
        retention_db,
        NodeStat,
        now - timedelta(days=30),
        batch_size=2,
        max_rows=3,
    )

    assert deleted == 3
    remaining = await retention_db.scalar(select(func.count()).select_from(NodeStat))
    assert remaining == 2


def test_cleanup_settings_support_independent_disabled_rules():
    settings = CleanupSettings(
        expired_users_retention_days=None,
        usage_history_retention_days=120,
        node_stats_retention_days=None,
    )

    assert settings.model_dump() == {
        "expired_users_retention_days": None,
        "usage_history_retention_days": 120,
        "node_stats_retention_days": None,
    }


def test_cleanup_settings_allows_immediate_expired_user_deletion():
    settings = CleanupSettings(expired_users_retention_days=0)

    assert settings.expired_users_retention_days == 0


@pytest.mark.parametrize("invalid_days", [0, -1, 36_501, 1.5])
def test_cleanup_settings_rejects_invalid_retention_days(invalid_days):
    with pytest.raises(ValidationError):
        CleanupSettings(usage_history_retention_days=invalid_days)


@pytest.mark.parametrize("invalid_interval", [0, -1])
def test_cleanup_retention_job_rejects_non_positive_intervals(invalid_interval):
    with pytest.raises(ValidationError):
        JobSettings.model_validate({"JOB_CLEANUP_RETENTION_INTERVAL": invalid_interval})
