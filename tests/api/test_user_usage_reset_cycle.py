import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.crud.bulk import reset_all_users_data_usage
from app.db.crud.user import (
    bulk_reset_user_data_usage,
    get_user,
    get_users_to_reset_data_usage,
    reset_user_by_next,
    reset_user_data_usage,
)
from app.db.models import (
    Admin,
    DataLimitResetStrategy,
    NextPlan,
    User,
    UserStatus,
    UserTemplate,
    UserUsageResetLogs,
    UserUsageResetSource,
)
from app.models.proxy import ProxyTable
from tests.api import DATABASE_URL, TestSession


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "strategy,days",
    [
        (DataLimitResetStrategy.day, 1),
        (DataLimitResetStrategy.week, 7),
        (DataLimitResetStrategy.month, 30),
        (DataLimitResetStrategy.year, 365),
    ],
)
@pytest.mark.parametrize("bulk", [False, True])
async def test_manual_reset_preserves_each_cycle_and_scheduled_reset_advances_it(strategy, days, bulk):
    async with TestSession() as session:
        user = User(username=f"cycle_{uuid4().hex[:16]}", used_traffic=123, data_limit_reset_strategy=strategy)
        user.created_at = datetime.now(UTC) - timedelta(days=days + 2)
        session.add(user)
        await session.commit()
        if bulk:
            await bulk_reset_user_data_usage(session, [user])
        else:
            await reset_user_data_usage(session, user)
        assert user.used_traffic == 0
        assert user.lifetime_used_traffic == 123
        assert user.last_cycle_traffic_reset_at is None
        assert user.last_traffic_reset_at is not None
        assert user.next_traffic_reset_at.date() == (user.created_at + timedelta(days=days)).date()
        assert [u.id for u in await get_users_to_reset_data_usage(session, user_ids=[user.id])] == [user.id]
        reset = await bulk_reset_user_data_usage(session, [user], reset_source=UserUsageResetSource.scheduled)
        assert [u.id for u in reset] == [user.id]
        assert user.usage_logs[-1].reset_source == "scheduled"
        assert user.last_cycle_traffic_reset_at == user.last_traffic_reset_at
        assert user.next_traffic_reset_at.date() == (datetime.now(UTC) + timedelta(days=days)).date()
        assert user.lifetime_used_traffic == 123
        assert await get_users_to_reset_data_usage(session, user_ids=[user.id]) == []


@pytest.mark.asyncio
async def test_scoped_reset_all_retains_history_lifetime_and_status_without_advancing_cycle():
    async with TestSession() as session:
        admin = Admin(username=f"reset_{uuid4().hex[:12]}", hashed_password="unused", role_id=3)
        session.add(admin)
        await session.flush()
        user = User(
            username=f"all_{uuid4().hex[:16]}",
            admin_id=admin.id,
            used_traffic=200,
            status=UserStatus.disabled,
            data_limit_reset_strategy=DataLimitResetStrategy.week,
        )
        user.created_at = datetime.now(UTC) - timedelta(days=10)
        outside = User(username=f"outside_{uuid4().hex[:16]}", used_traffic=55)
        session.add_all([user, outside])
        await session.flush()
        prior = UserUsageResetLogs(user_id=user.id, used_traffic_at_reset=100, reset_source="scheduled")
        prior.reset_at = datetime.now(UTC) - timedelta(days=8)
        session.add(prior)
        session.add(NextPlan(user_id=user.id, user_template_id=None, data_limit=900))
        await session.commit()
        await reset_all_users_data_usage(session, admin)
        await session.refresh(user)
        await user.awaitable_attrs.usage_logs
        await user.awaitable_attrs.next_plan
        await session.refresh(outside)
        assert user.status == UserStatus.disabled
        assert user.used_traffic == 0
        assert user.lifetime_used_traffic == 300
        assert [(log.used_traffic_at_reset, log.reset_source) for log in user.usage_logs] == [
            (100, "scheduled"),
            (200, "manual"),
        ]
        assert user.last_cycle_traffic_reset_at == prior.reset_at
        assert user.next_plan is None  # Existing manual reset policy remains unchanged.
        assert outside.used_traffic == 55


@pytest.mark.asyncio
@pytest.mark.parametrize("with_template", [False, True])
async def test_next_plan_keeps_existing_policy_and_starts_a_new_cycle(with_template):
    async with TestSession() as session:
        user = User(
            username=f"next_{uuid4().hex[:16]}",
            data_limit=100,
            used_traffic=10,
            data_limit_reset_strategy=DataLimitResetStrategy.month,
            proxy_settings=ProxyTable().dict(no_obj=True),
        )
        user.created_at = datetime.now(UTC) - timedelta(days=40)
        session.add(user)
        await session.flush()
        template_id = None
        if with_template:
            template = UserTemplate(
                name=f"next_tpl_{uuid4().hex[:12]}",
                username_prefix=None,
                username_suffix=None,
                extra_settings=None,
                groups=[],
                data_limit=1000,
                data_limit_reset_strategy=DataLimitResetStrategy.week,
            )
            session.add(template)
            await session.flush()
            template_id = template.id
        session.add(
            NextPlan(user_id=user.id, user_template_id=template_id, data_limit=1000, add_remaining_traffic=True)
        )
        await session.commit()
        user = await get_user(session, user.username)
        await reset_user_by_next(session, user)
        assert user.next_plan is None
        assert user.used_traffic == 0
        assert user.data_limit == 1090
        assert user.lifetime_used_traffic == 10
        assert user.usage_logs[-1].reset_source == "next_plan"
        assert user.last_cycle_traffic_reset_at == user.last_traffic_reset_at
        assert user.data_limit_reset_strategy == (
            DataLimitResetStrategy.week if with_template else DataLimitResetStrategy.month
        )
        assert (
            user.next_traffic_reset_at.date() == (datetime.now(UTC) + timedelta(days=7 if with_template else 30)).date()
        )
        assert await get_users_to_reset_data_usage(session, user_ids=[user.id]) == []


@pytest.mark.asyncio
async def test_optimized_reset_dates_match_history_and_refresh_after_manual_reset():
    async with TestSession() as session:
        user = User(username=f"dates_{uuid4().hex[:16]}", data_limit_reset_strategy=DataLimitResetStrategy.month)
        session.add(user)
        await session.flush()
        scheduled = UserUsageResetLogs(user_id=user.id, used_traffic_at_reset=10, reset_source="scheduled")
        scheduled.reset_at = datetime.now(UTC) - timedelta(days=5)
        session.add(scheduled)
        await session.commit()
        user = await get_user(session, user.username, load_usage_logs=False, load_lifetime_used_traffic=True)
        assert user.last_cycle_traffic_reset_at == user.last_traffic_reset_at
        assert user.last_cycle_traffic_reset_at.replace(tzinfo=UTC) == scheduled.reset_at.replace(tzinfo=UTC)
        await reset_user_data_usage(session, user)
        assert user.last_traffic_reset_at.replace(tzinfo=UTC) > user.last_cycle_traffic_reset_at.replace(tzinfo=UTC)
        assert user.last_cycle_traffic_reset_at.replace(tzinfo=UTC) == scheduled.reset_at.replace(tzinfo=UTC)


@pytest.mark.asyncio
async def test_no_reset_strategy_has_no_next_date_and_is_never_scheduled():
    async with TestSession() as session:
        user = User(username=f"no_cycle_{uuid4().hex[:16]}", used_traffic=50)
        user.created_at = datetime.now(UTC) - timedelta(days=400)
        session.add(user)
        await session.commit()
        await reset_user_data_usage(session, user)
        assert user.next_traffic_reset_at is None
        assert await get_users_to_reset_data_usage(session, user_ids=[user.id]) == []


@pytest.mark.asyncio
@pytest.mark.skipif(not DATABASE_URL.startswith("mysql"), reason="requires MySQL/MariaDB REPEATABLE READ")
@pytest.mark.parametrize("winner_source", [UserUsageResetSource.manual, UserUsageResetSource.scheduled])
async def test_mysql_repeatable_read_scheduler_waits_for_current_reset(winner_source):
    engine = create_async_engine(DATABASE_URL, isolation_level="REPEATABLE READ")
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    user_id = None
    try:
        async with sessions() as seed:
            user = User(
                username=f"rr_reset_{uuid4().hex[:16]}",
                used_traffic=100,
                data_limit_reset_strategy=DataLimitResetStrategy.day,
            )
            user.created_at = datetime.now(UTC) - timedelta(days=2)
            seed.add(user)
            await seed.commit()
            user_id = user.id
        async with sessions() as stale, sessions() as winner:
            candidates = await get_users_to_reset_data_usage(stale, user_ids=[user_id])
            assert len(candidates) == 1
            # Keep this transaction/snapshot open while the winner changes both
            # User and usage history. The loser must really wait for its lock.
            winning_user = await winner.get(User, user_id)
            await reset_user_data_usage(winner, winning_user, reset_source=winner_source, commit=False)
            await winner.flush()
            locking_read_started = asyncio.Event()

            def on_statement(_conn, _cursor, statement, _params, _context, _many):
                if "FOR UPDATE" in statement.upper():
                    locking_read_started.set()

            event.listen(engine.sync_engine, "before_cursor_execute", on_statement)
            pending = asyncio.create_task(
                bulk_reset_user_data_usage(stale, candidates, reset_source=UserUsageResetSource.scheduled)
            )
            try:
                await asyncio.wait_for(locking_read_started.wait(), timeout=10)
                assert not pending.done()
                await winner.commit()
                reset = await asyncio.wait_for(pending, timeout=15)
            finally:
                event.remove(engine.sync_engine, "before_cursor_execute", on_statement)
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
            assert [u.id for u in reset] == ([user_id] if winner_source is UserUsageResetSource.manual else [])
        async with sessions() as verify:
            logs = (
                await verify.scalars(
                    select(UserUsageResetLogs)
                    .where(UserUsageResetLogs.user_id == user_id)
                    .order_by(UserUsageResetLogs.id)
                )
            ).all()
            assert sum(log.used_traffic_at_reset for log in logs) == 100
            assert sum(log.reset_source == "scheduled" for log in logs) == 1
            assert [log.reset_source for log in logs] == (
                ["manual", "scheduled"] if winner_source is UserUsageResetSource.manual else ["scheduled"]
            )
    finally:
        if user_id is not None:
            async with sessions() as cleanup:
                await cleanup.execute(delete(User).where(User.id == user_id))
                await cleanup.commit()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.skipif(not DATABASE_URL.startswith("mysql"), reason="requires MySQL/MariaDB REPEATABLE READ")
async def test_mysql_repeatable_read_next_plan_activation_uses_current_values():
    engine = create_async_engine(DATABASE_URL, isolation_level="REPEATABLE READ")
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    user_id = None
    try:
        async with sessions() as seed:
            user = User(
                username=f"rr_next_{uuid4().hex[:16]}",
                data_limit=100,
                used_traffic=10,
                data_limit_reset_strategy=DataLimitResetStrategy.month,
            )
            seed.add(user)
            await seed.flush()
            user_id = user.id
            seed.add(NextPlan(user_id=user.id, user_template_id=None, data_limit=1000, add_remaining_traffic=True))
            await seed.commit()
        async with sessions() as stale:
            old_user = await get_user(stale, user.username)
            assert old_user.next_plan.data_limit == 1000
            async with sessions() as writer:
                current = await get_user(writer, user.username)
                current.used_traffic = 20
                current.next_plan.data_limit = 2000
                await writer.commit()
            # Ordinary reads still see the old snapshot and identity map.
            assert (await get_user(stale, user.username)).next_plan.data_limit == 1000
            result = await reset_user_by_next(stale, old_user)
            assert result.data_limit == 2080
            assert result.used_traffic == 0
            assert result.usage_logs[-1].used_traffic_at_reset == 20
            assert result.usage_logs[-1].reset_source == "next_plan"
            assert result.next_plan is None
    finally:
        if user_id is not None:
            async with sessions() as cleanup:
                await cleanup.execute(delete(User).where(User.id == user_id))
                await cleanup.commit()
        await engine.dispose()
