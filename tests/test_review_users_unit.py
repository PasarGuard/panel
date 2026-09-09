"""Expire/limit review jobs sync users in bulk instead of per row."""

from __future__ import annotations

from datetime import UTC, datetime as dt, timedelta as td
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import base
from app.db.crud.user import get_active_to_expire_users, start_users_expire
from app.db.models import User, UserStatus, UserUsageResetLogs
from app.jobs import review_users
from app.models.settings import HWIDSettings
from app.operation import OperatorType
from app.operation.subscription import SubscriptionOperation


def _user(user_id: int, *, next_plan=None) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, username=f"u{user_id}", next_plan=next_plan)


@pytest.mark.asyncio
async def test_apply_status_changes_syncs_plain_users_in_one_call():
    users = [_user(1), _user(2), _user(3)]

    async def _validate(db_user, include_subscription_url=True):
        return SimpleNamespace(id=db_user.id, username=db_user.username)

    with (
        patch("app.jobs.review_users.update_users_status", new_callable=AsyncMock) as update_status,
        patch("app.jobs.review_users.sync_users", new_callable=AsyncMock) as sync,
        patch.object(review_users.user_operator, "validate_user", side_effect=_validate),
        patch("app.jobs.review_users.notification.user_status_change", new_callable=AsyncMock) as status_change,
        patch("app.jobs.review_users.reset_user_by_next", new_callable=AsyncMock) as reset_next,
    ):
        await review_users.apply_status_changes(AsyncMock(), users, UserStatus.expired)

    update_status.assert_awaited_once()
    assert update_status.await_args.args[1] == users
    sync.assert_awaited_once_with(users)
    reset_next.assert_not_called()
    assert status_change.call_count == 3


@pytest.mark.asyncio
async def test_apply_status_changes_resets_next_plan_users_separately():
    next_plan = SimpleNamespace(data_limit=1)
    plain = _user(1)
    planned = _user(2, next_plan=next_plan)
    reset_user = _user(2)
    reset_user.status = UserStatus.active

    async def _validate(db_user, include_subscription_url=True):
        return SimpleNamespace(id=db_user.id, username=db_user.username)

    with (
        patch("app.jobs.review_users.update_users_status", new_callable=AsyncMock) as update_status,
        patch("app.jobs.review_users.sync_users", new_callable=AsyncMock) as sync,
        patch.object(review_users.user_operator, "validate_user", side_effect=_validate),
        patch("app.jobs.review_users.notification.user_status_change", new_callable=AsyncMock),
        patch("app.jobs.review_users.notification.user_data_reset_by_next", new_callable=AsyncMock) as reset_notify,
        patch(
            "app.jobs.review_users.reset_user_by_next", new_callable=AsyncMock, return_value=reset_user
        ) as reset_next,
    ):
        await review_users.apply_status_changes(AsyncMock(), [plain, planned], UserStatus.limited)

    update_status.assert_awaited_once()
    assert update_status.await_args.args[1] == [plain]
    reset_next.assert_awaited_once()
    assert [call.args[0] for call in sync.await_args_list] == [[plain], [reset_user]]
    reset_notify.assert_called_once()


@pytest.mark.asyncio
async def test_apply_status_changes_skips_status_update_when_already_active():
    users = [_user(1)]
    with (
        patch("app.jobs.review_users.update_users_status", new_callable=AsyncMock) as update_status,
        patch("app.jobs.review_users.sync_users", new_callable=AsyncMock) as sync,
        patch.object(
            review_users.user_operator,
            "validate_user",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(id=1, username="u1"),
        ),
        patch("app.jobs.review_users.notification.user_status_change", new_callable=AsyncMock),
    ):
        await review_users.apply_status_changes(AsyncMock(), users, UserStatus.active)

    update_status.assert_not_called()
    sync.assert_awaited_once_with(users)


@pytest.fixture
async def db_session():
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


@pytest.mark.asyncio
async def test_expire_query_skips_usage_logs(db_session):
    user = User(username="expiring", status=UserStatus.active)
    user.expire = dt.now(UTC) - td(hours=1)
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserUsageResetLogs(user_id=user.id, used_traffic_at_reset=9))
    await db_session.commit()

    expired = await get_active_to_expire_users(db_session)
    assert len(expired) == 1
    assert "usage_logs" in sa_inspect(expired[0]).unloaded
    assert expired[0].lifetime_used_traffic == 9


@pytest.mark.asyncio
async def test_start_users_expire_updates_all_rows_in_one_statement(db_session):
    users = [
        User(username="hold1", status=UserStatus.on_hold, on_hold_expire_duration=3600),
        User(username="hold2", status=UserStatus.on_hold, on_hold_expire_duration=7200),
    ]
    db_session.add_all(users)
    await db_session.commit()

    updated = await start_users_expire(db_session, users)
    assert all(user.status == UserStatus.active for user in updated)
    assert all(user.on_hold_expire_duration is None for user in updated)
    assert updated[0].expire is not None
    assert updated[1].expire is not None


@pytest.mark.asyncio
async def test_existing_hwid_skips_register_when_recently_used():
    op = SubscriptionOperation(OperatorType.API)
    existing = SimpleNamespace(last_used_at=dt.now(UTC) - td(seconds=30))
    settings = HWIDSettings(enabled=True, forced=False, fallback_limit=3)

    with (
        patch("app.operation.subscription.hwid_settings", new_callable=AsyncMock, return_value=settings),
        patch("app.operation.subscription.get_user_hwid_by_value", new_callable=AsyncMock, return_value=existing),
        patch("app.operation.subscription.register_user_hwid", new_callable=AsyncMock) as register,
    ):
        await op.validate_and_register_hwid(AsyncMock(), 1, None, None, "device-1", None, None, None)

    register.assert_not_called()


@pytest.mark.asyncio
async def test_existing_hwid_registers_when_stale():
    op = SubscriptionOperation(OperatorType.API)
    existing = SimpleNamespace(last_used_at=dt.now(UTC) - td(minutes=10))
    settings = HWIDSettings(enabled=True, forced=False, fallback_limit=3)

    with (
        patch("app.operation.subscription.hwid_settings", new_callable=AsyncMock, return_value=settings),
        patch("app.operation.subscription.get_user_hwid_by_value", new_callable=AsyncMock, return_value=existing),
        patch("app.operation.subscription.register_user_hwid", new_callable=AsyncMock) as register,
    ):
        await op.validate_and_register_hwid(AsyncMock(), 1, None, None, "device-1", "iOS", "16", "iPhone")

    register.assert_awaited_once()
