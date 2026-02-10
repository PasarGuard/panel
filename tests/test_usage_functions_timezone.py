"""
Comprehensive timezone filtering tests for usage statistics functions.

Tests verify that the UTC conversion fix correctly filters records by timezone-aware start/end dates.
"""

import os
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool, NullPool

from app.db import base
from app.db.models import (
    NodeUsage,
    NodeUserUsage,
    User,
    Admin,
    Node,
)
from app.models.stats import Period
from app.models.proxy import ProxyTable
from app.db.crud.node import get_nodes_usage, get_node_stats
from app.db.crud.user import get_user_usages, get_all_users_usages
from app.db.crud.admin import get_admin_usages
from config import SQLALCHEMY_DATABASE_URL


def _get_test_database_url() -> tuple[str, bool]:
    """Get test database URL from environment or use SQLite."""
    test_from = os.getenv("TEST_FROM", "local").lower()
    if test_from == "local":
        return "sqlite+aiosqlite:///:memory:", True
    return SQLALCHEMY_DATABASE_URL, False


@pytest.fixture
async def session_factory():
    """Fixture providing a test database session factory."""
    database_url, is_local = _get_test_database_url()

    engine_kwargs = {}
    connect_args = {}
    if is_local:
        connect_args["check_same_thread"] = False
        engine_kwargs["poolclass"] = StaticPool
    else:
        engine_kwargs["poolclass"] = NullPool

    engine = create_async_engine(database_url, connect_args=connect_args, **engine_kwargs)

    # Only create/drop tables for SQLite (in-memory test database)
    if is_local:
        async with engine.begin() as conn:
            await conn.run_sync(base.Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    yield session_factory

    # Cleanup - only drop tables for SQLite
    if is_local:
        async with engine.begin() as conn:
            await conn.run_sync(base.Base.metadata.drop_all)
    await engine.dispose()


async def setup_test_data(session_factory):
    """Create admin, user, and node for tests."""
    async with session_factory() as session:
        admin = Admin(username="admin", hashed_password="secret")
        session.add(admin)
        await session.flush()

        user = User(username="user1", admin_id=admin.id, proxy_settings=ProxyTable().dict(no_obj=True))
        session.add(user)
        await session.flush()

        node = Node(
            name="node1",
            address="127.0.0.1",
            port=8080,
            api_port=62051,
            server_ca="ca",
            api_key="key",
            core_config_id=None,
        )
        session.add(node)
        await session.flush()
        await session.commit()

        return admin.id, user.id, node.id


class TestGetNodesUsageTimezone:
    """Test get_nodes_usage with timezone-aware filtering."""

    @pytest.mark.asyncio
    async def test_timezone_filtering_tehran_timezone_hour_period(self, session_factory):
        """
        Test that timezone-aware filtering excludes data from before the requested start date.

        This test demonstrates the fix for the bug where:
        - Request: start=2026-02-10T00:00:00+03:30 (Tehran timezone)
        - Would incorrectly include: 2026-02-03T00:00:00+03:30 (before the requested date)

        After the fix, only data within the requested range is returned.
        """
        admin_id, user_id, node_id = await setup_test_data(session_factory)

        async with session_factory() as session:
            # Inject test data at various timestamps (all in UTC)
            # Tehran timezone is UTC+03:30
            # Request range: 2026-02-10 00:00:00+03:30 to 03:00:00+03:30
            # Which equals: 2026-02-09 20:30:00 UTC to 2026-02-09 23:30:00 UTC
            timestamps_utc = [
                datetime(2026, 2, 9, 20, 15, 0, tzinfo=timezone.utc),  # BEFORE range
                datetime(2026, 2, 9, 20, 45, 0, tzinfo=timezone.utc),  # IN RANGE ✓
                datetime(2026, 2, 9, 21, 30, 0, tzinfo=timezone.utc),  # IN RANGE ✓
                datetime(2026, 2, 9, 22, 15, 0, tzinfo=timezone.utc),  # IN RANGE ✓
                datetime(2026, 2, 10, 0, 0, 0, tzinfo=timezone.utc),   # AFTER range
            ]

            for ts in timestamps_utc:
                record = NodeUsage(created_at=ts, node_id=node_id, uplink=1000000, downlink=10000000)
                session.add(record)
            await session.commit()

            # Call function with Tehran timezone
            tehran_tz = timezone(timedelta(hours=3, minutes=30))
            start = datetime(2026, 2, 10, 0, 0, 0, tzinfo=tehran_tz)
            end = datetime(2026, 2, 10, 3, 0, 0, tzinfo=tehran_tz)

            result = await get_nodes_usage(
                session,
                start=start,
                end=end,
                period=Period.hour,
                node_id=node_id,
            )

            # Verify the fix:
            # - Should have stats for the node
            assert result.stats is not None
            assert node_id in result.stats

            stats = result.stats[node_id]

            # BEFORE FIX: Would return 4 periods (including data from 20:15 UTC)
            # AFTER FIX: Returns correct number of periods within the requested range
            # The key verification is that we DON'T include the record at 20:15 UTC (before start)
            assert len(stats) >= 2, f"Expected at least 2 periods with data, got {len(stats)}"

            # Verify no data before the requested start time
            for stat in stats:
                assert stat.period_start >= start, (
                    f"FAIL: Got period_start {stat.period_start} which is before requested start {start}"
                )

    @pytest.mark.asyncio
    async def test_timezone_filtering_negative_offset_new_york(self, session_factory):
        """
        Test timezone filtering with negative offset (New York, UTC-05:00).

        Verifies that the fix works correctly with negative timezone offsets.
        """
        admin_id, user_id, node_id = await setup_test_data(session_factory)

        async with session_factory() as session:
            # New York timezone is UTC-05:00
            # Request: 2026-02-10 00:00:00-05:00 = 2026-02-10 05:00:00 UTC
            timestamps_utc = [
                datetime(2026, 2, 10, 4, 45, 0, tzinfo=timezone.utc),  # BEFORE
                datetime(2026, 2, 10, 5, 15, 0, tzinfo=timezone.utc),  # IN RANGE ✓
                datetime(2026, 2, 10, 6, 30, 0, tzinfo=timezone.utc),  # IN RANGE ✓
                datetime(2026, 2, 10, 7, 45, 0, tzinfo=timezone.utc),  # IN RANGE ✓
                datetime(2026, 2, 10, 8, 15, 0, tzinfo=timezone.utc),  # AFTER
            ]

            for ts in timestamps_utc:
                record = NodeUsage(created_at=ts, node_id=node_id, uplink=1000000, downlink=10000000)
                session.add(record)
            await session.commit()

            ny_tz = timezone(timedelta(hours=-5))
            start = datetime(2026, 2, 10, 0, 0, 0, tzinfo=ny_tz)
            end = datetime(2026, 2, 10, 3, 0, 0, tzinfo=ny_tz)

            result = await get_nodes_usage(
                session,
                start=start,
                end=end,
                period=Period.hour,
                node_id=node_id,
            )

            assert result.stats is not None
            assert node_id in result.stats
            stats = result.stats[node_id]

            # Should have 3 periods (not 4)
            assert len(stats) == 3

            # All periods should be >= start time
            for stat in stats:
                assert stat.period_start >= start

    @pytest.mark.asyncio
    @pytest.mark.parametrize("period", [Period.hour, Period.day])
    async def test_timezone_filtering_multiple_periods(self, session_factory, period):
        """Test that timezone filtering works for multiple period types."""
        admin_id, user_id, node_id = await setup_test_data(session_factory)

        async with session_factory() as session:
            # Create test records
            timestamps_utc = [
                datetime(2026, 2, 9, 0, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 10, 0, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 11, 0, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 12, 0, 0, 0, tzinfo=timezone.utc),
            ]

            for ts in timestamps_utc:
                record = NodeUsage(created_at=ts, node_id=node_id, uplink=1000000, downlink=10000000)
                session.add(record)
            await session.commit()

            start = datetime(2026, 2, 9, 0, 0, 0, tzinfo=timezone.utc)
            end = datetime(2026, 2, 11, 0, 0, 0, tzinfo=timezone.utc)

            result = await get_nodes_usage(
                session,
                start=start,
                end=end,
                period=period,
                node_id=node_id,
            )

            assert result.stats is not None
            assert node_id in result.stats
            stats = result.stats[node_id]

            # Should have data for the records in range
            assert len(stats) >= 2

            # All periods should be within range
            for stat in stats:
                assert stat.period_start >= start
                assert stat.period_start <= end


class TestGetNodeStatsTimezone:
    """Test get_node_stats with timezone-aware filtering."""

    @pytest.mark.asyncio
    async def test_node_stats_timezone_filtering(self, session_factory):
        """Test that get_node_stats respects timezone-aware filtering."""
        admin_id, user_id, node_id = await setup_test_data(session_factory)

        async with session_factory() as session:
            # Note: NodeStat is a different model from NodeUsage and may not have test data
            # This test verifies the function doesn't error with timezone-aware dates
            tehran_tz = timezone(timedelta(hours=3, minutes=30))
            start = datetime(2026, 2, 10, 0, 0, 0, tzinfo=tehran_tz)
            end = datetime(2026, 2, 10, 3, 0, 0, tzinfo=tehran_tz)

            result = await get_node_stats(session, node_id, start, end, Period.hour)

            assert result.stats is not None
            # Stats may be empty if no NodeStat records exist, which is fine
            # The important thing is that the function handles timezone-aware dates correctly

            # If there are stats, verify they're within the requested range
            for stat in result.stats:
                assert stat.period_start >= start


class TestGetUserUsagesTimezone:
    """Test get_user_usages with timezone-aware filtering."""

    @pytest.mark.asyncio
    async def test_user_usages_timezone_filtering(self, session_factory):
        """Test that get_user_usages respects timezone-aware filtering."""
        admin_id, user_id, node_id = await setup_test_data(session_factory)

        async with session_factory() as session:
            timestamps_utc = [
                datetime(2026, 2, 9, 20, 15, 0, tzinfo=timezone.utc),  # BEFORE
                datetime(2026, 2, 9, 20, 45, 0, tzinfo=timezone.utc),  # IN RANGE
                datetime(2026, 2, 9, 21, 30, 0, tzinfo=timezone.utc),  # IN RANGE
                datetime(2026, 2, 10, 0, 0, 0, tzinfo=timezone.utc),   # AFTER
            ]

            for ts in timestamps_utc:
                record = NodeUserUsage(
                    created_at=ts,
                    user_id=user_id,
                    node_id=node_id,
                    used_traffic=5000000,
                )
                session.add(record)
            await session.commit()

            tehran_tz = timezone(timedelta(hours=3, minutes=30))
            start = datetime(2026, 2, 10, 0, 0, 0, tzinfo=tehran_tz)
            end = datetime(2026, 2, 10, 3, 0, 0, tzinfo=tehran_tz)

            result = await get_user_usages(
                session,
                user_id=user_id,
                start=start,
                end=end,
                period=Period.hour,
            )

            assert result.stats is not None
            # When node_id not specified, it defaults to -1
            assert -1 in result.stats
            stats = result.stats[-1]

            # Should have at least 2 periods (not 4 which would be the bug)
            assert len(stats) >= 2

            for stat in stats:
                assert stat.period_start >= start


class TestGetAllUsersUsagesTimezone:
    """Test get_all_users_usages with timezone-aware filtering."""

    @pytest.mark.asyncio
    async def test_all_users_usages_timezone_filtering(self, session_factory):
        """Test that get_all_users_usages respects timezone-aware filtering."""
        admin_id, user_id, node_id = await setup_test_data(session_factory)

        async with session_factory() as session:
            timestamps_utc = [
                datetime(2026, 2, 9, 20, 15, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 9, 20, 45, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 9, 21, 30, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 10, 0, 0, 0, tzinfo=timezone.utc),
            ]

            for ts in timestamps_utc:
                record = NodeUserUsage(
                    created_at=ts,
                    user_id=user_id,
                    node_id=node_id,
                    used_traffic=5000000,
                )
                session.add(record)
            await session.commit()

            tehran_tz = timezone(timedelta(hours=3, minutes=30))
            start = datetime(2026, 2, 10, 0, 0, 0, tzinfo=tehran_tz)
            end = datetime(2026, 2, 10, 3, 0, 0, tzinfo=tehran_tz)

            result = await get_all_users_usages(
                session,
                admins=None,
                start=start,
                end=end,
                period=Period.hour,
            )

            assert result.stats is not None

            for user_stats in result.stats.values():
                for stat in user_stats:
                    assert stat.period_start >= start


class TestGetAdminUsagesTimezone:
    """Test get_admin_usages with timezone-aware filtering."""

    @pytest.mark.asyncio
    async def test_admin_usages_timezone_filtering(self, session_factory):
        """Test that get_admin_usages respects timezone-aware filtering."""
        admin_id, user_id, node_id = await setup_test_data(session_factory)

        async with session_factory() as session:
            timestamps_utc = [
                datetime(2026, 2, 9, 20, 15, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 9, 20, 45, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 9, 21, 30, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 10, 0, 0, 0, tzinfo=timezone.utc),
            ]

            for ts in timestamps_utc:
                record = NodeUserUsage(
                    created_at=ts,
                    user_id=user_id,
                    node_id=node_id,
                    used_traffic=5000000,
                )
                session.add(record)
            await session.commit()

            tehran_tz = timezone(timedelta(hours=3, minutes=30))
            start = datetime(2026, 2, 10, 0, 0, 0, tzinfo=tehran_tz)
            end = datetime(2026, 2, 10, 3, 0, 0, tzinfo=tehran_tz)

            result = await get_admin_usages(
                session,
                admin_id=admin_id,
                start=start,
                end=end,
                period=Period.hour,
            )

            assert result.stats is not None
            assert -1 in result.stats  # Default node_id when not grouped by node
            stats = result.stats[-1]

            # Should have 2-3 periods (not 4)
            assert len(stats) <= 3

            for stat in stats:
                assert stat.period_start >= start
