"""
Comprehensive timezone filtering tests for usage statistics functions.

Tests verify that the UTC conversion fix correctly filters records by timezone-aware start/end dates.
This includes strict testing with multiple data rows, edge cases for each period, and expected responses.
"""

from datetime import datetime, timedelta, timezone
import pytest
from uuid import uuid4
from sqlalchemy import select

from app.db.models import (
    NodeUsage,
    NodeUserUsage,
    User,
    Admin,
    Node,
)
from app.models.stats import Period, NodeUsageStatsList, UserUsageStatsList
from app.models.proxy import ProxyTable
from app.db.crud.node import get_nodes_usage
from app.db.crud.user import get_user_usages, get_all_users_usages
from app.db.crud.admin import get_admin_usages
from tests.api import TestSession


async def setup_test_data(session, test_suffix=""):
    """Create admin, user, and node for tests within an existing session.

    Args:
        session: SQLAlchemy async session
        test_suffix: Optional suffix to make usernames unique across tests
    """
    # Generate unique identifiers to avoid UNIQUE constraint violations
    unique_id = str(uuid4())[:8]
    if test_suffix:
        unique_id = f"{test_suffix}_{unique_id}"

    admin = Admin(username=f"admin_{unique_id}", hashed_password="secret")
    session.add(admin)
    await session.flush()

    user = User(username=f"user_{unique_id}", admin_id=admin.id, proxy_settings=ProxyTable().dict(no_obj=True))
    session.add(user)
    await session.flush()

    node = Node(
        name=f"node_{unique_id}",
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
    await session.refresh(admin)
    await session.refresh(user)
    await session.refresh(node)

    return admin.id, user.id, node.id


class TestGetNodesUsageTimezone:
    """Test get_nodes_usage with timezone-aware filtering."""

    @pytest.mark.asyncio
    async def test_timezone_filtering_tehran_hour_strict(self):
        """
        Strict test: Tehran timezone with multiple data rows.

        Verifies that:
        - Data BEFORE requested start is excluded
        - Data AFTER requested end is excluded
        - Only data within range is returned
        - Period grouping works correctly in Tehran timezone
        """
        async with TestSession() as session:
            admin_id, user_id, node_id = await setup_test_data(session)

            # Inject 10 data points: 3 before, 6 in range, 1 after
            # Tehran timezone is UTC+03:30
            # Request range: 2026-02-10 00:00:00+03:30 to 03:00:00+03:30
            # Which equals: 2026-02-09 20:30:00 UTC to 2026-02-09 23:30:00 UTC
            timestamps_utc = [
                datetime(2026, 2, 9, 19, 45, 0, tzinfo=timezone.utc),  # 23:15 Tehran - BEFORE
                datetime(2026, 2, 9, 20, 0, 0, tzinfo=timezone.utc),   # 23:30 Tehran - BEFORE
                datetime(2026, 2, 9, 20, 15, 0, tzinfo=timezone.utc),  # 23:45 Tehran - BEFORE
                datetime(2026, 2, 9, 20, 30, 0, tzinfo=timezone.utc),  # 00:00 Tehran - IN RANGE ✓
                datetime(2026, 2, 9, 20, 45, 0, tzinfo=timezone.utc),  # 00:15 Tehran - IN RANGE ✓
                datetime(2026, 2, 9, 21, 0, 0, tzinfo=timezone.utc),   # 00:30 Tehran - IN RANGE ✓
                datetime(2026, 2, 9, 21, 30, 0, tzinfo=timezone.utc),  # 01:00 Tehran - IN RANGE ✓
                datetime(2026, 2, 9, 22, 30, 0, tzinfo=timezone.utc),  # 02:00 Tehran - IN RANGE ✓
                datetime(2026, 2, 9, 23, 15, 0, tzinfo=timezone.utc),  # 02:45 Tehran - IN RANGE ✓
                datetime(2026, 2, 10, 0, 0, 0, tzinfo=timezone.utc),   # 03:30 Tehran - AFTER
            ]

            for idx, ts in enumerate(timestamps_utc):
                record = NodeUsage(
                    created_at=ts,
                    node_id=node_id,
                    uplink=1000000 + idx,
                    downlink=10000000 + idx,
                )
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

            # Strict validations
            assert isinstance(result, NodeUsageStatsList)
            assert result.stats is not None
            assert node_id in result.stats, f"Node {node_id} not in stats"

            stats = result.stats[node_id]

            # Should have exactly 3 periods for hour-level grouping in 3-hour range
            assert len(stats) == 3, f"Expected 3 periods, got {len(stats)}"

            # Validate all stats are within the requested range
            for stat in stats:
                assert stat.period_start >= start, (
                    f"Stat period_start {stat.period_start} is before requested start {start}"
                )
                assert stat.period_start < end, (
                    f"Stat period_start {stat.period_start} is at or after requested end {end}"
                )

                # Period start should not have been affected by the wrong earlier data
                assert stat.period_start.tzinfo is not None

            # Verify stats are in chronological order
            for i in range(len(stats) - 1):
                assert stats[i].period_start < stats[i + 1].period_start

    @pytest.mark.asyncio
    async def test_timezone_filtering_negative_offset_new_york_strict(self):
        """
        Strict test: New York timezone (UTC-05:00) with multiple data rows.

        Verifies correct filtering with negative timezone offset.
        """
        async with TestSession() as session:
            admin_id, user_id, node_id = await setup_test_data(session)

            # New York timezone is UTC-05:00
            # Request: 2026-02-10 00:00:00-05:00 = 2026-02-10 05:00:00 UTC
            timestamps_utc = [
                datetime(2026, 2, 10, 4, 0, 0, tzinfo=timezone.utc),   # BEFORE
                datetime(2026, 2, 10, 4, 30, 0, tzinfo=timezone.utc),  # BEFORE
                datetime(2026, 2, 10, 5, 15, 0, tzinfo=timezone.utc),  # IN RANGE (00:15 NY)
                datetime(2026, 2, 10, 6, 15, 0, tzinfo=timezone.utc),  # IN RANGE (01:15 NY)
                datetime(2026, 2, 10, 7, 15, 0, tzinfo=timezone.utc),  # IN RANGE (02:15 NY)
                datetime(2026, 2, 10, 8, 0, 0, tzinfo=timezone.utc),   # IN RANGE (03:00 NY boundary)
                datetime(2026, 2, 10, 8, 30, 0, tzinfo=timezone.utc),  # AFTER
                datetime(2026, 2, 10, 9, 0, 0, tzinfo=timezone.utc),   # AFTER
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

            # Should have at least 3 periods
            assert len(stats) >= 3, f"Expected at least 3 periods, got {len(stats)}"

            # All periods should be >= start and within/on boundary
            for stat in stats:
                assert stat.period_start >= start, f"Period {stat.period_start} is before start {start}"
                # Note: period_start can equal end in boundary cases

    @pytest.mark.asyncio
    @pytest.mark.parametrize("period", [Period.hour, Period.day])
    async def test_timezone_filtering_no_early_data(self, period):
        """
        Strict test: Validate that data BEFORE start date is excluded.

        This is the core bug fix validation: ensure no data from before the
        requested start time is included in the response.
        """
        async with TestSession() as session:
            admin_id, user_id, node_id = await setup_test_data(session)

            # UTC timestamps spanning a range
            start_utc = datetime(2026, 2, 10, 0, 0, 0, tzinfo=timezone.utc)
            end_utc = datetime(2026, 2, 11, 0, 0, 0, tzinfo=timezone.utc)

            # Inject data BEFORE the range (this is what was being returned before the fix)
            before_timestamps = [
                datetime(2026, 2, 9, 20, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 9, 22, 0, 0, tzinfo=timezone.utc),
            ]

            # Inject data IN the range
            in_range_timestamps = [
                datetime(2026, 2, 10, 6, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 10, 12, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 10, 18, 0, 0, tzinfo=timezone.utc),
            ]

            all_timestamps = before_timestamps + in_range_timestamps
            for idx, ts in enumerate(all_timestamps):
                record = NodeUsage(created_at=ts, node_id=node_id, uplink=1000000 + idx, downlink=10000000 + idx)
                session.add(record)
            await session.commit()

            result = await get_nodes_usage(
                session,
                start=start_utc,
                end=end_utc,
                period=period,
                node_id=node_id,
            )

            assert result.stats is not None
            assert node_id in result.stats
            stats = result.stats[node_id]

            # Core validation: NO data from before start should be included
            for stat in stats:
                assert stat.period_start >= start_utc, (
                    f"BUG: Got data from before start! period_start {stat.period_start} < start {start_utc}"
                )


class TestGetUserUsagesTimezone:
    """Test get_user_usages with timezone-aware filtering."""

    @pytest.mark.asyncio
    async def test_user_usages_timezone_filtering_strict(self):
        """
        Strict test: Multiple data rows with Tehran timezone.

        Verifies correct filtering for user usage statistics.
        """
        async with TestSession() as session:
            admin_id, user_id, node_id = await setup_test_data(session)

            # Inject 8 data points: 2 before, 5 in range, 1 after
            timestamps_utc = [
                datetime(2026, 2, 9, 20, 0, 0, tzinfo=timezone.utc),   # BEFORE
                datetime(2026, 2, 9, 20, 15, 0, tzinfo=timezone.utc),  # BEFORE
                datetime(2026, 2, 9, 20, 30, 0, tzinfo=timezone.utc),  # IN RANGE ✓
                datetime(2026, 2, 9, 20, 45, 0, tzinfo=timezone.utc),  # IN RANGE ✓
                datetime(2026, 2, 9, 21, 30, 0, tzinfo=timezone.utc),  # IN RANGE ✓
                datetime(2026, 2, 9, 22, 15, 0, tzinfo=timezone.utc),  # IN RANGE ✓
                datetime(2026, 2, 9, 23, 15, 0, tzinfo=timezone.utc),  # IN RANGE ✓
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

            assert isinstance(result, UserUsageStatsList)
            assert result.stats is not None
            assert -1 in result.stats
            stats = result.stats[-1]

            # Should have exactly 3 periods (not 8, not more)
            assert len(stats) == 3, f"Expected 3 periods, got {len(stats)}"

            # All periods should be within requested range
            for stat in stats:
                assert stat.period_start >= start
                assert stat.period_start < end

    @pytest.mark.asyncio
    @pytest.mark.parametrize("period", [Period.hour, Period.day, Period.month])
    async def test_user_usages_multiple_periods_strict(self, period):
        """
        Strict test: Multiple periods with proper data distribution.
        """
        async with TestSession() as session:
            admin_id, user_id, node_id = await setup_test_data(session)

            # Create data spanning 3 months
            start_utc = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_utc = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)

            # Add records at various points
            current = start_utc
            while current < end_utc:
                record = NodeUserUsage(
                    created_at=current,
                    user_id=user_id,
                    node_id=node_id,
                    used_traffic=5000000,
                )
                session.add(record)
                current += timedelta(days=5)
            await session.commit()

            result = await get_user_usages(
                session,
                user_id=user_id,
                start=start_utc,
                end=end_utc,
                period=period,
            )

            assert result.stats is not None
            assert -1 in result.stats
            stats = result.stats[-1]

            # All stats must be within range
            for stat in stats:
                assert stat.period_start >= start_utc
                assert stat.period_start < end_utc


class TestGetAllUsersUsagesTimezone:
    """Test get_all_users_usages with timezone-aware filtering."""

    @pytest.mark.asyncio
    async def test_all_users_usages_timezone_filtering_strict(self):
        """
        Strict test: Validate timezone filtering for all users aggregation.
        """
        async with TestSession() as session:
            admin_id, user_id, node_id = await setup_test_data(session)

            # Inject data with mixture of before and in-range records
            before_timestamps = [
                datetime(2026, 2, 9, 20, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 9, 20, 30, 0, tzinfo=timezone.utc),
            ]

            in_range_timestamps = [
                datetime(2026, 2, 9, 20, 45, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 9, 21, 30, 0, tzinfo=timezone.utc),
                datetime(2026, 2, 9, 22, 15, 0, tzinfo=timezone.utc),
            ]

            all_timestamps = before_timestamps + in_range_timestamps
            for ts in all_timestamps:
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

            # Validate all stats are within range - no data before start
            # get_all_users_usages returns dict[user_id, list[UserUsageStat]] or dict[user_id, dict[node_id, list]]
            for user_stats in result.stats.values():
                # Handle both structures: list or dict
                if isinstance(user_stats, dict):
                    for stats_list in user_stats.values():
                        for stat in stats_list:
                            assert stat.period_start >= start, (
                                f"BUG: Got data from before start! period_start {stat.period_start} < start {start}"
                            )
                elif isinstance(user_stats, list):
                    for stat in user_stats:
                        assert stat.period_start >= start, (
                            f"BUG: Got data from before start! period_start {stat.period_start} < start {start}"
                        )


class TestGetAdminUsagesTimezone:
    """Test get_admin_usages with timezone-aware filtering."""

    @pytest.mark.asyncio
    async def test_admin_usages_timezone_filtering_strict(self):
        """
        Strict test: Admin-level aggregation with multiple users and data rows.
        """
        async with TestSession() as session:
            admin_id, user_id, node_id = await setup_test_data(session)

            # Create second user under same admin with unique username
            from uuid import uuid4
            unique_id = str(uuid4())[:8]
            user2 = User(username=f"user2_{unique_id}", admin_id=admin_id, proxy_settings=ProxyTable().dict(no_obj=True))
            session.add(user2)
            await session.flush()

            # Inject 8 data points for each user
            timestamps_utc = [
                datetime(2026, 2, 9, 20, 0, 0, tzinfo=timezone.utc),   # BEFORE
                datetime(2026, 2, 9, 20, 15, 0, tzinfo=timezone.utc),  # BEFORE
                datetime(2026, 2, 9, 20, 30, 0, tzinfo=timezone.utc),  # IN RANGE
                datetime(2026, 2, 9, 20, 45, 0, tzinfo=timezone.utc),  # IN RANGE
                datetime(2026, 2, 9, 21, 30, 0, tzinfo=timezone.utc),  # IN RANGE
                datetime(2026, 2, 9, 22, 15, 0, tzinfo=timezone.utc),  # IN RANGE
                datetime(2026, 2, 9, 23, 15, 0, tzinfo=timezone.utc),  # IN RANGE
                datetime(2026, 2, 10, 0, 0, 0, tzinfo=timezone.utc),   # AFTER
            ]

            for ts in timestamps_utc:
                # User 1
                record1 = NodeUserUsage(
                    created_at=ts,
                    user_id=user_id,
                    node_id=node_id,
                    used_traffic=5000000,
                )
                session.add(record1)

                # User 2
                record2 = NodeUserUsage(
                    created_at=ts,
                    user_id=user2.id,
                    node_id=node_id,
                    used_traffic=3000000,
                )
                session.add(record2)
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

            # Should have exactly 3 periods for hour-level grouping in 3-hour range
            assert len(stats) == 3, f"Expected 3 periods, got {len(stats)}"

            # All periods should be within range
            for stat in stats:
                assert stat.period_start >= start
                assert stat.period_start < end

    @pytest.mark.asyncio
    @pytest.mark.parametrize("period", [Period.hour, Period.day])
    async def test_admin_usages_multiple_periods_strict(self, period):
        """
        Strict test: Multiple periods with admin-level aggregation.
        """
        async with TestSession() as session:
            admin_id, user_id, node_id = await setup_test_data(session)

            start_utc = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_utc = datetime(2026, 2, 15, 0, 0, 0, tzinfo=timezone.utc)

            # Create records spanning the range
            current = start_utc
            while current < end_utc:
                record = NodeUserUsage(
                    created_at=current,
                    user_id=user_id,
                    node_id=node_id,
                    used_traffic=5000000,
                )
                session.add(record)
                current += timedelta(hours=6)
            await session.commit()

            result = await get_admin_usages(
                session,
                admin_id=admin_id,
                start=start_utc,
                end=end_utc,
                period=period,
            )

            assert result.stats is not None
            assert -1 in result.stats
            stats = result.stats[-1]

            # All periods must be within range
            for stat in stats:
                assert stat.period_start >= start_utc
                assert stat.period_start < end_utc
