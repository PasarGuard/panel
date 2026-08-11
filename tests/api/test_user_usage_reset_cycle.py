from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.crud.user import (
    bulk_reset_user_data_usage,
    get_users_to_reset_data_usage,
    reset_user_data_usage,
)
from app.db.models import (
    DataLimitResetStrategy,
    User,
    UserUsageResetLogs,
    UserUsageResetSource,
)
from app.models.proxy import ProxyTable
from tests.api import TestSession


@pytest.mark.asyncio
async def test_legacy_reset_is_only_used_until_a_scheduled_reset_exists():
    now = datetime.now(UTC)

    async with TestSession() as session:
        def make_user(label: str) -> User:
            user = User(
                username=f"{label}_reset_cycle_{uuid4().hex[:8]}",
                data_limit_reset_strategy=DataLimitResetStrategy.month,
                proxy_settings=ProxyTable().dict(no_obj=True),
            )
            user.created_at = now - timedelta(days=61)
            return user

        manual_reset_user = make_user("manual")
        recent_scheduled_user = make_user("recent_scheduled")
        recent_legacy_user = make_user("recent_legacy")
        old_legacy_user = make_user("old_legacy")
        scheduled_with_later_noise_user = make_user("scheduled_with_later_noise")

        session.add_all(
            [
                manual_reset_user,
                recent_scheduled_user,
                recent_legacy_user,
                old_legacy_user,
                scheduled_with_later_noise_user,
            ]
        )
        await session.flush()
        await session.execute(
            delete(UserUsageResetLogs).where(
                UserUsageResetLogs.user_id.in_(
                    [
                        manual_reset_user.id,
                        recent_scheduled_user.id,
                        recent_legacy_user.id,
                        old_legacy_user.id,
                        scheduled_with_later_noise_user.id,
                    ]
                )
            )
        )

        def make_log(user: User, source: UserUsageResetSource, days_ago: int) -> UserUsageResetLogs:
            log = UserUsageResetLogs(
                user_id=user.id,
                used_traffic_at_reset=1024,
                reset_source=source.value,
            )
            log.reset_at = now - timedelta(days=days_ago)
            return log

        session.add_all(
            [
                make_log(manual_reset_user, UserUsageResetSource.manual, 1),
                make_log(recent_scheduled_user, UserUsageResetSource.scheduled, 1),
                make_log(recent_legacy_user, UserUsageResetSource.legacy, 1),
                make_log(old_legacy_user, UserUsageResetSource.legacy, 31),
                make_log(scheduled_with_later_noise_user, UserUsageResetSource.scheduled, 31),
                make_log(scheduled_with_later_noise_user, UserUsageResetSource.legacy, 1),
                make_log(scheduled_with_later_noise_user, UserUsageResetSource.manual, 1),
            ]
        )
        await session.commit()

        users_to_reset = await get_users_to_reset_data_usage(session)
        user_ids_to_reset = {user.id for user in users_to_reset}

        assert manual_reset_user.id in user_ids_to_reset
        assert recent_scheduled_user.id not in user_ids_to_reset
        assert recent_legacy_user.id not in user_ids_to_reset
        assert old_legacy_user.id in user_ids_to_reset
        assert scheduled_with_later_noise_user.id in user_ids_to_reset

        await session.refresh(recent_legacy_user, attribute_names=["usage_logs"])
        await session.refresh(scheduled_with_later_noise_user, attribute_names=["usage_logs"])
        assert recent_legacy_user.next_traffic_reset_at.date() == (now + timedelta(days=29)).date()
        assert scheduled_with_later_noise_user.next_traffic_reset_at.date() == (now - timedelta(days=1)).date()


@pytest.mark.asyncio
async def test_stale_scheduler_user_does_not_double_count_manual_reset():
    username = f"reset_race_{uuid4().hex[:8]}"

    async with TestSession() as scheduler_session:
        user = User(
            username=username,
            used_traffic=100,
            data_limit_reset_strategy=DataLimitResetStrategy.day,
            proxy_settings=ProxyTable().dict(no_obj=True),
        )
        user.created_at = datetime.now(UTC) - timedelta(days=2)
        scheduler_session.add(user)
        await scheduler_session.commit()
        stale_user = await scheduler_session.get(User, user.id)
        await scheduler_session.commit()
        assert stale_user.used_traffic == 100

        async with TestSession() as manual_session:
            manual_user = await manual_session.get(User, user.id)
            await reset_user_data_usage(manual_session, manual_user)

        # The scheduler still holds the pre-reset ORM object. The row-locking
        # reset must refresh it before lifetime traffic is logged.
        await reset_user_data_usage(
            scheduler_session,
            stale_user,
            reset_source=UserUsageResetSource.scheduled,
        )

        total_reset_traffic = await scheduler_session.scalar(
            select(func.sum(UserUsageResetLogs.used_traffic_at_reset)).where(UserUsageResetLogs.user_id == user.id)
        )
        assert total_reset_traffic == 100


@pytest.mark.asyncio
async def test_scheduler_rechecks_due_state_after_locking_stale_candidates():
    username = f"scheduler_recheck_{uuid4().hex[:8]}"

    async with TestSession() as stale_scheduler_session:
        user = User(
            username=username,
            used_traffic=100,
            data_limit_reset_strategy=DataLimitResetStrategy.day,
            proxy_settings=ProxyTable().dict(no_obj=True),
        )
        user.created_at = datetime.now(UTC) - timedelta(days=2)
        stale_scheduler_session.add(user)
        await stale_scheduler_session.commit()

        stale_candidates = await get_users_to_reset_data_usage(stale_scheduler_session, user_ids=[user.id])
        assert [candidate.id for candidate in stale_candidates] == [user.id]
        await stale_scheduler_session.commit()

        async with TestSession() as winning_scheduler_session:
            winning_user = await winning_scheduler_session.get(User, user.id)
            reset_users = await bulk_reset_user_data_usage(
                winning_scheduler_session,
                [winning_user],
                reset_source=UserUsageResetSource.scheduled,
            )
            assert [reset_user.id for reset_user in reset_users] == [user.id]

        reset_users = await bulk_reset_user_data_usage(
            stale_scheduler_session,
            stale_candidates,
            reset_source=UserUsageResetSource.scheduled,
        )
        assert reset_users == []

        scheduled_log_count = await stale_scheduler_session.scalar(
            select(func.count(UserUsageResetLogs.id)).where(
                UserUsageResetLogs.user_id == user.id,
                UserUsageResetLogs.reset_source == UserUsageResetSource.scheduled.value,
            )
        )
        assert scheduled_log_count == 1
