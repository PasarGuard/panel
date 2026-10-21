"""Data-usage resets keep traffic recorded while they run, and the bulk reset costs the same few statements for any
number of users. Runs on SQLite by default and on PostgreSQL/MySQL/MariaDB with TEST_FROM=github."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import DateTime, event, func, literal, select

from app.db.compiles_types import DateDiff
from app.db.crud.user import (
    bulk_reset_user_data_usage,
    get_user_by_id,
    get_users_to_reset_data_usage,
    refresh_and_load_user,
    reset_user_data_usage,
)
from app.db.models import (
    DataLimitResetStrategy,
    NextPlan,
    NodeUserUsage,
    NotificationReminder,
    ReminderType,
    User,
    UserStatus,
    UserUsageResetLogs,
)
from app.jobs import record_usages
from app.models.proxy import ProxyTable
from tests.test_record_usages import reset_user_usage_history_buffer, session_factory  # noqa: F401


@pytest.fixture(autouse=True)
def clear_dialect_cache():
    record_usages._dialect_cache.clear()
    yield
    record_usages._dialect_cache.clear()


def _user(username: str, **kwargs) -> User:
    user = User(username=username, proxy_settings=ProxyTable().dict(no_obj=True), **kwargs)
    user.created_at = datetime.now(UTC) - timedelta(days=40)
    return user


async def _lifetime(session_factory, user_id: int) -> tuple[int, int]:  # noqa: F811
    async with session_factory() as db:
        used = (await db.execute(select(User.used_traffic).where(User.id == user_id))).scalar_one()
        logged = (
            await db.execute(
                select(func.coalesce(func.sum(UserUsageResetLogs.used_traffic_at_reset), 0)).where(
                    UserUsageResetLogs.user_id == user_id
                )
            )
        ).scalar_one()
    return int(used), int(logged)


@pytest.mark.asyncio
async def test_reset_job_keeps_traffic_recorded_after_users_were_loaded(session_factory):  # noqa: F811
    async with session_factory() as db:
        db_user = _user(
            "daily", used_traffic=1_000, data_limit=10_000, data_limit_reset_strategy=DataLimitResetStrategy.day
        )
        db.add(db_user)
        await db.commit()
        user_id = db_user.id

    async with session_factory() as db:
        users = await get_users_to_reset_data_usage(db)
        assert [user.id for user in users] == [user_id]
        # record_usages commits more traffic on its own connection before the reset is written
        await record_usages.update_users_traffic([{"uid": user_id, "value": 500}])
        reset_users = await bulk_reset_user_data_usage(db, users)
        assert [user.used_traffic for user in reset_users] == [0]
        assert [user.lifetime_used_traffic for user in reset_users] == [1_500]

    assert await _lifetime(session_factory, user_id) == (0, 1_500)


@pytest.mark.asyncio
async def test_single_reset_keeps_traffic_recorded_after_user_was_loaded(session_factory):  # noqa: F811
    async with session_factory() as db:
        db_user = _user("single", used_traffic=1_000, data_limit=10_000)
        db.add(db_user)
        await db.flush()
        db.add(NextPlan(user_id=db_user.id, user_template_id=None, data_limit=5_000))
        await db.commit()
        user_id = db_user.id

    async with session_factory() as db:
        db_user = await get_user_by_id(db, user_id)
        assert db_user.next_plan is not None
        await record_usages.update_users_traffic([{"uid": user_id, "value": 500}])
        db_user = await reset_user_data_usage(db, db_user)
        assert (db_user.used_traffic, db_user.next_plan) == (0, None)
        assert db_user.lifetime_used_traffic == 1_500

    assert await _lifetime(session_factory, user_id) == (0, 1_500)


@pytest.mark.asyncio
async def test_uncommitted_single_reset_leaves_the_loaded_user_consistent(session_factory):  # noqa: F811
    async with session_factory() as db:
        db_user = _user("template", used_traffic=2_000, data_limit=1_000, status=UserStatus.limited)
        db.add(db_user)
        await db.flush()
        db.add(NextPlan(user_id=db_user.id, user_template_id=None, data_limit=5_000))
        await db.commit()
        user_id = db_user.id

    async with session_factory() as db:
        db_user = await get_user_by_id(db, user_id)
        assert db_user.next_plan is not None
        # Template flows reset first and modify the same object before one commit
        await reset_user_data_usage(db, db_user, commit=False)
        assert (db_user.used_traffic, db_user.status, db_user.next_plan) == (0, UserStatus.active, None)
        db_user.next_plan = NextPlan(user_id=user_id, user_template_id=None, data_limit=7_000)
        await db.commit()

    async with session_factory() as db:
        plans = (await db.execute(select(NextPlan.data_limit).where(NextPlan.user_id == user_id))).scalars().all()
    assert plans == [7_000]
    assert await _lifetime(session_factory, user_id) == (0, 2_000)


async def _seed_reset_cases(db, prefix: str) -> list[int]:
    """One user per reset case; the same cases are seeded under two prefixes to compare two implementations."""
    cases = [
        {"used_traffic": 0, "status": UserStatus.active},
        {"used_traffic": 300, "data_limit": 1_000, "status": UserStatus.active},
        {"used_traffic": 1_500, "data_limit": 1_000, "status": UserStatus.limited},
        {"used_traffic": 700, "data_limit": 1_000, "status": UserStatus.disabled},
        {"used_traffic": 900, "data_limit": 1_000, "status": UserStatus.expired},
        {"used_traffic": 800, "status": UserStatus.on_hold},
        {"used_traffic": 2_000, "data_limit": 2_000, "status": UserStatus.limited},
    ]
    users = [_user(f"{prefix}{index}", **case) for index, case in enumerate(cases)]
    db.add_all(users)
    await db.flush()
    now = datetime.now(UTC).replace(microsecond=0)
    for index, user in enumerate(users):
        if index % 2 == 0:
            db.add(
                NextPlan(
                    user_id=user.id,
                    user_template_id=None,
                    data_limit=10_000 + index,
                    add_remaining_traffic=bool(index % 4),
                )
            )
        if index % 3 == 0:
            db.add(UserUsageResetLogs(user_id=user.id, used_traffic_at_reset=111 * (index + 1)))
        for threshold in (None, 0, 50, 80):
            db.add(NotificationReminder(user_id=user.id, type=ReminderType.data_usage, threshold=threshold))
        db.add(NotificationReminder(user_id=user.id, type=ReminderType.expiration_date, threshold=3))
        for bucket in range(index % 3):
            db.add(
                NodeUserUsage(
                    created_at=now - timedelta(minutes=10 * bucket), user_id=user.id, node_id=None, used_traffic=5
                )
            )
    await db.commit()
    return [user.id for user in users]


async def _reset_state(db, user_ids: list[int]) -> list[tuple]:
    """Everything a reset touches, keyed by the user's case index instead of its id."""
    index_of = {user_id: index for index, user_id in enumerate(user_ids)}
    users = (
        await db.execute(select(User.id, User.used_traffic, User.status, User.data_limit).where(User.id.in_(user_ids)))
    ).all()
    logs = (
        await db.execute(
            select(UserUsageResetLogs.user_id, UserUsageResetLogs.used_traffic_at_reset).where(
                UserUsageResetLogs.user_id.in_(user_ids)
            )
        )
    ).all()
    plans = (await db.execute(select(NextPlan.user_id).where(NextPlan.user_id.in_(user_ids)))).all()
    reminders = (
        await db.execute(
            select(NotificationReminder.user_id, NotificationReminder.type, NotificationReminder.threshold).where(
                NotificationReminder.user_id.in_(user_ids)
            )
        )
    ).all()
    usages = (await db.execute(select(NodeUserUsage.user_id).where(NodeUserUsage.user_id.in_(user_ids)))).all()
    return [
        sorted((index_of[row.id], row.used_traffic, row.status, row.data_limit) for row in users),
        sorted((index_of[row.user_id], row.used_traffic_at_reset) for row in logs),
        sorted(index_of[row.user_id] for row in plans),
        sorted((index_of[row.user_id], row.type, -1 if row.threshold is None else row.threshold) for row in reminders),
        sorted(index_of[row.user_id] for row in usages),
    ]


async def _per_user_reset(db, users: list[User], *, clean_chart_data: bool) -> list[User]:
    """The per-user reset that bulk_reset_user_data_usage ran before it became set-based (reference only)."""
    for db_user in users:
        await db_user.awaitable_attrs.next_plan
        db.add(UserUsageResetLogs(user_id=db_user.id, used_traffic_at_reset=db_user.used_traffic))
        if db_user.next_plan:
            await db.delete(db_user.next_plan)
            db_user.next_plan = None
        db_user.used_traffic = 0
        await db.execute(
            NotificationReminder.__table__.delete().where(
                NotificationReminder.user_id == db_user.id,
                NotificationReminder.type == ReminderType.data_usage,
                NotificationReminder.threshold > 0,
            )
        )
        if clean_chart_data:
            await db.execute(NodeUserUsage.__table__.delete().where(NodeUserUsage.user_id == db_user.id))
        if db_user.status == UserStatus.limited:
            db_user.status = UserStatus.active
    await db.commit()
    for db_user in users:
        await refresh_and_load_user(db, db_user, load_admin_role=True)
    return users


def _returned_state(users: list[User], user_ids: list[int]) -> list[tuple]:
    index_of = {user_id: index for index, user_id in enumerate(user_ids)}
    return sorted(
        (index_of[user.id], user.used_traffic, user.status, user.next_plan, user.lifetime_used_traffic)
        for user in users
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("clean_chart_data", [False, True])
async def test_bulk_reset_matches_the_per_user_reset(session_factory, clean_chart_data):  # noqa: F811
    async with session_factory() as db:
        reference_ids = await _seed_reset_cases(db, "reference")
        bulk_ids = await _seed_reset_cases(db, "bulk")

    async with session_factory() as db:
        reference_users = [await get_user_by_id(db, user_id) for user_id in reference_ids]
        reference_returned = _returned_state(
            await _per_user_reset(db, reference_users, clean_chart_data=clean_chart_data), reference_ids
        )
    async with session_factory() as db:
        bulk_users = [await get_user_by_id(db, user_id, load_usage_logs=False) for user_id in bulk_ids]
        bulk_returned = _returned_state(
            await bulk_reset_user_data_usage(db, bulk_users, clean_chart_data=clean_chart_data), bulk_ids
        )

    async with session_factory() as db:
        reference_state = await _reset_state(db, reference_ids)
        bulk_state = await _reset_state(db, bulk_ids)

    assert bulk_state == reference_state
    assert bulk_returned == reference_returned
    # Sanity: the cases cover status flips, plan removal and reminder cleanup
    assert [status for _, _, status, _ in bulk_state[0]].count(UserStatus.active) == 4
    assert bulk_state[2] == []
    assert {threshold for *_, threshold in bulk_state[3]} == {-1, 0, 3}


@pytest.mark.asyncio
async def test_bulk_reset_statement_count_does_not_grow_with_users(session_factory):  # noqa: F811
    async def statements_for(count: int, prefix: str) -> int:
        async with session_factory() as db:
            users = [
                _user(f"{prefix}{index}", used_traffic=10, data_limit=5, status=UserStatus.limited)
                for index in range(count)
            ]
            db.add_all(users)
            await db.flush()
            for user in users:
                db.add(NextPlan(user_id=user.id, user_template_id=None, data_limit=100))
                db.add(UserUsageResetLogs(user_id=user.id, used_traffic_at_reset=1))
                db.add(NotificationReminder(user_id=user.id, type=ReminderType.data_usage, threshold=80))
            await db.commit()
            user_ids = [user.id for user in users]

        async with session_factory() as db:
            users = [await get_user_by_id(db, user_id, load_usage_logs=False) for user_id in user_ids]
            statements = []
            sync_engine = db.bind.sync_engine

            def count(_conn, _cursor, statement, *_args):
                statements.append(statement)

            event.listen(sync_engine, "before_cursor_execute", count)
            try:
                reset_users = await bulk_reset_user_data_usage(db, users, clean_chart_data=True)
            finally:
                event.remove(sync_engine, "before_cursor_execute", count)
            assert {user.status for user in reset_users} == {UserStatus.active}
            assert {user.lifetime_used_traffic for user in reset_users} == {11}
        return len(statements)

    few = await statements_for(3, "few")
    many = await statements_for(40, "many")
    assert many == few, f"{few} statements for 3 users, {many} for 40"


@pytest.mark.asyncio
async def test_reset_cycle_length_is_elapsed_time_on_every_database(session_factory):  # noqa: F811
    def at(*args):
        return literal(datetime(*args), DateTime())

    async with session_factory() as db:
        across_midnight, within_one_date = (
            await db.execute(
                select(
                    DateDiff(at(2026, 10, 22, 0, 0, 5), at(2026, 10, 21, 23, 59, 55)),
                    DateDiff(at(2026, 10, 22, 23, 59, 0), at(2026, 10, 22, 0, 1, 0)),
                )
            )
        ).one()
    # A daily cycle is due after 1 day: 10 seconds across midnight are not a day, 23h58m on one date almost are
    assert float(across_midnight) < 0.001
    assert 0.99 < float(within_one_date) < 1
