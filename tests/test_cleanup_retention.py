import importlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.crud.user import autodelete_expired_users
from app.db.models import NodeOutboundUsage, NodeStat, NodeUsage, NodeUserUsage, User, UserStatus
from app.jobs.cleanup_retention import delete_expired_rows_in_batches
from app.models.settings import CleanupSettings

cleanup_retention_job = importlib.import_module("app.jobs.cleanup_retention")
cleanup_retention_migration = importlib.import_module(
    "app.db.migrations.versions.f0420da90ff1_add_cleanup_retention_settings"
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
    ("env_values", "expected"),
    [
        ({}, {}),
        ({"USERS_AUTODELETE_DAYS": "-1"}, {}),
        ({"USERS_AUTODELETE_DAYS": "0"}, {"expired_users_retention_days": 0}),
        ({"USERS_AUTODELETE_DAYS": " 30 "}, {"expired_users_retention_days": 30}),
        ({"USERS_AUTODELETE_DAYS": "40000"}, {"expired_users_retention_days": 36_500}),
        ({"USERS_AUTODELETE_DAYS": "soon"}, {}),
        ({"USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS": "True"}, {"include_limited_users": True}),
        ({"USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS": "0"}, {"include_limited_users": False}),
        ({"USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS": "maybe"}, {}),
    ],
)
def test_migration_moves_autodelete_env_vars(env_values, expected):
    """Set env vars become cleanup settings; nothing else is written, so retention stays off."""
    cleanup = cleanup_retention_migration.build_cleanup(env_values)
    assert cleanup == expected
    CleanupSettings.model_validate(cleanup)


def test_migration_reads_environment_before_dotenv():
    values = cleanup_retention_migration.read_env_values(
        environ={"users_autodelete_days": "7"},
        dotenv={"USERS_AUTODELETE_DAYS": "3", "USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS": "true", "OTHER": "1"},
    )
    assert values == {"USERS_AUTODELETE_DAYS": "7", "USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS": "true"}


def test_cleanup_settings_default_keeps_everything():
    """Automatic cleanup is opt-in: an install that never saved the section deletes nothing."""
    assert CleanupSettings().model_dump() == {
        "expired_users_retention_days": None,
        "include_limited_users": False,
        "usage_history_retention_days": None,
        "node_stats_retention_days": None,
    }


def test_cleanup_settings_support_independent_disabled_rules():
    """Allow each cleanup rule to be disabled independently."""
    settings = CleanupSettings(
        expired_users_retention_days=None,
        usage_history_retention_days=120,
        node_stats_retention_days=None,
    )

    assert settings.model_dump() == {
        "expired_users_retention_days": None,
        "include_limited_users": False,
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
async def test_expired_user_cleanup_revalidates_selected_users(retention_db, monkeypatch):
    """Keep a selected user that becomes ineligible before the locking read."""
    user = User(
        username="expired-cleanup-concurrent-update",
        status=UserStatus.expired,
        last_status_change=datetime.now(UTC) - timedelta(days=2),
        proxy_settings={},
    )
    retention_db.add(user)
    await retention_db.commit()

    original_scalars = retention_db.scalars

    async def scalars_with_status_change(statement, *args, **kwargs):
        """Make the candidate active immediately before eligibility is revalidated."""
        if getattr(statement, "_for_update_arg", None) is not None:
            await retention_db.execute(
                update(User)
                .where(User.id == user.id)
                .values(status=UserStatus.active, last_status_change=datetime.now(UTC))
            )
            await retention_db.flush()
        return await original_scalars(statement, *args, **kwargs)

    monkeypatch.setattr(retention_db, "scalars", scalars_with_status_change)

    deleted_users = await autodelete_expired_users(
        retention_db,
        default_autodelete_days=1,
        batch_size=10,
        max_users=10,
    )

    assert deleted_users == []
    assert await retention_db.scalar(select(func.count()).select_from(User)) == 1
    assert await retention_db.scalar(select(User.status).where(User.id == user.id)) is UserStatus.active


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
    ("retention_days", "include_limited"),
    [(None, False), (0, True)],
)
async def test_remove_expired_users_applies_disabled_and_immediate_modes(
    retention_db,
    monkeypatch,
    retention_days,
    include_limited,
):
    """Map disabled and immediate policies to the user deletion query."""
    settings_mock = AsyncMock(
        return_value=CleanupSettings(expired_users_retention_days=retention_days, include_limited_users=include_limited)
    )
    autodelete_mock = AsyncMock(return_value=[])
    db_context = MagicMock()
    db_context.__aenter__.return_value = retention_db

    monkeypatch.setattr(remove_expired_users_job, "cleanup_settings", settings_mock)
    monkeypatch.setattr(remove_expired_users_job, "autodelete_expired_users", autodelete_mock)
    monkeypatch.setattr(remove_expired_users_job, "GetDB", MagicMock(return_value=db_context))

    await remove_expired_users_job.remove_expired_users()

    autodelete_mock.assert_awaited_once_with(
        retention_db,
        include_limited,
        default_autodelete_days=retention_days,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("hours_ago", "deleted"), [(23, False), (25, True)])
async def test_expired_user_cleanup_uses_whole_days(retention_db, hours_ago, deleted):
    retention_db.add(
        User(
            username=f"expired-cleanup-boundary-{hours_ago}",
            status=UserStatus.expired,
            last_status_change=datetime.now(UTC) - timedelta(hours=hours_ago),
            proxy_settings={},
        )
    )
    await retention_db.commit()

    deleted_users = await autodelete_expired_users(retention_db, default_autodelete_days=1)

    assert len(deleted_users) == (1 if deleted else 0)


@pytest.mark.asyncio
async def test_expired_user_cleanup_without_policy_keeps_users(retention_db):
    retention_db.add(
        User(
            username="expired-cleanup-no-policy",
            status=UserStatus.expired,
            last_status_change=datetime.now(UTC) - timedelta(days=400),
            proxy_settings={},
        )
    )
    await retention_db.commit()

    assert await autodelete_expired_users(retention_db) == []


@pytest.mark.asyncio
async def test_cleanup_retention_job_deletes_old_usage_history(retention_db, monkeypatch):
    """Usage retention covers user, node and outbound usage rows."""
    now = datetime(2026, 10, 30, 12, tzinfo=UTC)
    old = (now - timedelta(days=11)).replace(tzinfo=None)
    recent = (now - timedelta(days=9)).replace(tzinfo=None)
    for created_at in (old, recent):
        retention_db.add_all(
            [
                NodeUserUsage(created_at=created_at, user_id=1, node_id=1, used_traffic=10),
                NodeUsage(created_at=created_at, node_id=1, uplink=1, downlink=2),
                NodeOutboundUsage(created_at=created_at, node_id=1, outbound_tag="direct", uplink=1, downlink=2),
            ]
        )
    await retention_db.commit()

    db_context = MagicMock()
    db_context.__aenter__.return_value = retention_db
    monkeypatch.setattr(
        cleanup_retention_job,
        "cleanup_settings",
        AsyncMock(return_value=CleanupSettings(usage_history_retention_days=10)),
    )
    monkeypatch.setattr(cleanup_retention_job, "GetDB", MagicMock(return_value=db_context))

    deleted = await cleanup_retention_job.cleanup_retention_data(now=now)

    assert deleted == {"node_user_usages": 1, "node_usages": 1, "node_outbound_usages": 1}
    for model in (NodeUserUsage, NodeUsage, NodeOutboundUsage):
        assert await retention_db.scalar(select(func.count()).select_from(model)) == 1


def test_elapsed_seconds_binds_are_not_cached():
    """A cached compile must not reuse the first statement's timestamp."""
    from sqlalchemy import DateTime, literal
    from sqlalchemy.dialects import postgresql

    from app.db.compiles_types import ElapsedSeconds

    first = datetime(2026, 1, 1, tzinfo=UTC)
    second = datetime(2026, 6, 1, tzinfo=UTC)
    statements = [
        select(User.id).where(ElapsedSeconds(literal(value, DateTime(timezone=True)), User.last_status_change) > 0)
        for value in (first, second)
    ]
    keys = [statement._generate_cache_key() for statement in statements]
    assert keys[0] == keys[1]
    bound = [bind.value for bind in keys[1].bindparams]
    assert second in bound and first not in bound
    compiled = statements[1].compile(dialect=postgresql.dialect())
    assert second in compiled.params.values()


@pytest.mark.asyncio
async def test_expired_user_cleanup_locks_subnets_before_users(retention_db, monkeypatch):
    """Subnet rows are locked before the user rows, the same order as the WireGuard allocation paths."""
    import app.db.crud.user as user_crud

    peer_settings = {"wireguard": {"peer_ips": ["10.8.0.5/32"]}}
    retention_db.add(
        User(
            username="expired-cleanup-wireguard",
            status=UserStatus.expired,
            last_status_change=datetime.now(UTC) - timedelta(days=2),
            proxy_settings=peer_settings,
        )
    )
    await retention_db.commit()

    calls = []

    async def record_lock(db, settings_list):
        calls.append(("subnets", list(settings_list)))

    original_remove = user_crud.remove_users

    async def record_remove(db, users):
        calls.append(("users", [user.username for user in users]))
        await original_remove(db, users)

    monkeypatch.setattr(user_crud, "lock_users_subnets", record_lock)
    monkeypatch.setattr(user_crud, "remove_users", record_remove)

    await autodelete_expired_users(retention_db, default_autodelete_days=1)

    assert calls == [("subnets", [peer_settings]), ("users", ["expired-cleanup-wireguard"])]


@pytest.mark.asyncio
async def test_expired_user_cleanup_retries_when_peer_ip_moves(retention_db, monkeypatch):
    """A peer IP that changes after the subnet lock makes the batch start over, locking the new subnet first."""
    import app.db.crud.user as user_crud

    old_settings = {"wireguard": {"peer_ips": ["10.8.0.5/32"]}}
    new_settings = {"wireguard": {"peer_ips": ["10.9.0.5/32"]}}
    user = User(
        username="expired-cleanup-moved-peer",
        status=UserStatus.expired,
        last_status_change=datetime.now(UTC) - timedelta(days=2),
        proxy_settings=old_settings,
    )
    retention_db.add(user)
    await retention_db.commit()

    locked = []

    async def move_after_first_lock(db, settings_list):
        locked.append(list(settings_list))
        if len(locked) == 1:
            await db.execute(update(User).where(User.id == user.id).values(proxy_settings=new_settings))
            await db.commit()

    monkeypatch.setattr(user_crud, "lock_users_subnets", move_after_first_lock)

    deleted_users = await autodelete_expired_users(retention_db, default_autodelete_days=1)

    assert locked == [[old_settings], [new_settings]]
    assert [deleted.username for deleted in deleted_users] == ["expired-cleanup-moved-peer"]
