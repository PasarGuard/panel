import importlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.crud.user import autodelete_expired_users
from app.db.models import NodeStat, User, UserStatus
from app.jobs.cleanup_retention import delete_expired_rows_in_batches
from app.models.settings import CleanupSettings
from config import JobSettings, UserCleanupSettings

cleanup_retention_job = importlib.import_module("app.jobs.cleanup_retention")
cleanup_retention_migration = importlib.import_module(
    "app.db.migrations.versions.7b3d1e9c4a6f_add_cleanup_retention_settings"
)
remove_expired_users_job = importlib.import_module("app.jobs.remove_expired_users")


@pytest.fixture
async def retention_db():
    """Provide an isolated in-memory database for retention tests."""
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
    """Build a node-stat row at a controlled timestamp."""
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
async def test_retention_delete_is_batched_and_preserves_recent_rows(retention_db, monkeypatch):
    """Delete old rows in bounded commits while retaining recent data."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
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

    commit_spy = AsyncMock(wraps=retention_db.commit)
    monkeypatch.setattr(retention_db, "commit", commit_spy)

    deleted = await delete_expired_rows_in_batches(
        retention_db,
        NodeStat,
        cutoff,
        batch_size=2,
        max_rows=10,
    )

    assert deleted == 3
    assert commit_spy.await_count == 2

    remaining_stats = (await retention_db.scalars(select(NodeStat))).all()
    assert len(remaining_stats) == 1
    remaining_created_at = remaining_stats[0].created_at
    if remaining_created_at.tzinfo is None:
        remaining_created_at = remaining_created_at.replace(tzinfo=UTC)
    assert remaining_created_at > cutoff


@pytest.mark.asyncio
async def test_retention_delete_honors_per_run_limit(retention_db):
    """Stop deleting once the configured per-run limit is reached."""
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


@pytest.mark.asyncio
async def test_retention_delete_does_not_include_rows_inserted_after_selection(retention_db, monkeypatch):
    """Leave a backdated row inserted after batch selection for the next run."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    retention_db.add_all(
        [
            _node_stat(1, now - timedelta(days=32)),
            _node_stat(2, now - timedelta(days=31)),
            _node_stat(3, now - timedelta(days=29)),
        ]
    )
    await retention_db.commit()

    original_execute = retention_db.execute
    inserted = False

    async def execute_with_concurrent_insert(statement, *args, **kwargs):
        """Insert a backdated row after the cleanup SELECT but before its DELETE."""
        nonlocal inserted
        result = await original_execute(statement, *args, **kwargs)
        if statement.is_select and not inserted:
            inserted = True
            retention_db.add(_node_stat(99, now - timedelta(days=33)))
            await retention_db.flush()
        return result

    monkeypatch.setattr(retention_db, "execute", execute_with_concurrent_insert)

    deleted = await delete_expired_rows_in_batches(
        retention_db,
        NodeStat,
        cutoff,
        batch_size=2,
        max_rows=2,
    )

    assert deleted == 2
    remaining_node_ids = set((await retention_db.scalars(select(NodeStat.node_id))).all())
    assert remaining_node_ids == {3, 99}


@pytest.mark.parametrize(
    ("legacy_days", "expected_days"),
    [(-1, None), (0, 0), (30, 30), (36_500, 36_500), (40_000, 36_500)],
)
def test_migration_normalizes_legacy_retention_days(legacy_days, expected_days):
    """Preserve valid legacy values and clamp values above the runtime limit."""
    assert cleanup_retention_migration.normalize_legacy_retention_days(legacy_days) == expected_days


def test_cleanup_settings_support_independent_disabled_rules():
    """Allow each cleanup rule to be disabled independently."""
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
    """Allow zero days for immediate expired-user deletion."""
    settings = CleanupSettings(expired_users_retention_days=0)

    assert settings.expired_users_retention_days == 0


@pytest.mark.parametrize("invalid_days", [0, -1, 36_501, 1.5])
def test_cleanup_settings_rejects_invalid_retention_days(invalid_days):
    """Reject invalid positive-day retention values."""
    with pytest.raises(ValidationError):
        CleanupSettings(usage_history_retention_days=invalid_days)


@pytest.mark.parametrize("invalid_interval", [0, -1])
def test_cleanup_retention_job_rejects_non_positive_intervals(invalid_interval):
    """Reject scheduler intervals that cannot make forward progress."""
    with pytest.raises(ValidationError):
        JobSettings.model_validate({"JOB_CLEANUP_RETENTION_INTERVAL": invalid_interval})


@pytest.mark.parametrize(
    "invalid_limit",
    [
        {"USER_AUTODELETE_BATCH_SIZE": 0},
        {"USER_AUTODELETE_MAX_USERS_PER_RUN": 0},
    ],
)
def test_user_cleanup_settings_reject_non_positive_limits(invalid_limit):
    """Reject batch limits that cannot make cleanup progress."""
    with pytest.raises(ValidationError):
        UserCleanupSettings.model_validate(invalid_limit)


@pytest.mark.asyncio
async def test_expired_user_cleanup_batches_and_leaves_backlog(retention_db, monkeypatch):
    """Delete only the per-run maximum and leave the backlog for a later run."""
    expired_at = datetime.now(UTC) - timedelta(days=2)
    retention_db.add_all(
        [
            User(
                username=f"expired-cleanup-{index}",
                status=UserStatus.expired,
                last_status_change=expired_at,
                proxy_settings={},
            )
            for index in range(5)
        ]
    )
    await retention_db.commit()

    commit_spy = AsyncMock(wraps=retention_db.commit)
    monkeypatch.setattr(retention_db, "commit", commit_spy)

    deleted_users = await autodelete_expired_users(
        retention_db,
        default_autodelete_days=1,
        batch_size=2,
        max_users=3,
    )

    assert len(deleted_users) == 3
    assert commit_spy.await_count == 2
    remaining = await retention_db.scalar(select(func.count()).select_from(User))
    assert remaining == 2


@pytest.mark.asyncio
async def test_cleanup_retention_job_skips_disabled_rules(retention_db, monkeypatch):
    """Skip all history deletions when both retention rules are disabled."""
    settings_mock = AsyncMock(
        return_value=CleanupSettings(
            usage_history_retention_days=None,
            node_stats_retention_days=None,
        )
    )
    delete_mock = AsyncMock()
    db_context = MagicMock()
    db_context.__aenter__.return_value = retention_db

    monkeypatch.setattr(cleanup_retention_job, "cleanup_settings", settings_mock)
    monkeypatch.setattr(cleanup_retention_job, "delete_expired_rows_in_batches", delete_mock)
    monkeypatch.setattr(cleanup_retention_job, "GetDB", MagicMock(return_value=db_context))

    deleted = await cleanup_retention_job.cleanup_retention_data()

    assert deleted == {}
    delete_mock.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("retention_days", "expected_fallback"),
    [(None, -1), (0, 0)],
)
async def test_remove_expired_users_applies_disabled_and_immediate_modes(
    retention_db,
    monkeypatch,
    retention_days,
    expected_fallback,
):
    """Map disabled and immediate policies to the user deletion query."""
    settings_mock = AsyncMock(return_value=CleanupSettings(expired_users_retention_days=retention_days))
    autodelete_mock = AsyncMock(return_value=[])
    db_context = MagicMock()
    db_context.__aenter__.return_value = retention_db

    monkeypatch.setattr(remove_expired_users_job, "cleanup_settings", settings_mock)
    monkeypatch.setattr(remove_expired_users_job, "autodelete_expired_users", autodelete_mock)
    monkeypatch.setattr(remove_expired_users_job, "GetDB", MagicMock(return_value=db_context))

    await remove_expired_users_job.remove_expired_users()

    autodelete_mock.assert_awaited_once_with(
        retention_db,
        remove_expired_users_job.user_cleanup_settings.include_limited_accounts,
        default_autodelete_days=expected_fallback,
        batch_size=remove_expired_users_job.user_cleanup_settings.autodelete_batch_size,
        max_users=remove_expired_users_job.user_cleanup_settings.autodelete_max_users_per_run,
    )
