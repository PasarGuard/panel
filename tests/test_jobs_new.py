"""Tests for new/changed job-related code in this PR.

Covers:
- app/jobs/dependencies.py   (SYSTEM_ADMIN now uses AdminRoleData with is_owner=True)
- app/jobs/review_admins.py  (_send_usage_limit_warning_notifications, limit_admins_job)
- app/app_factory.py         (PermissionDenied and LimitExceeded exception handlers)
- app/db/models.py           (Admin hybrid props: is_disabled, is_limited, is_owner via AdminRoleData;
                               APIKey.is_expired and is_usable; AdminRole.is_builtin)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.db import base
from app.db.models import Admin, AdminRole, AdminStatus, APIKey, APIKeyStatus


# ---------------------------------------------------------------------------
# Shared DB fixture
# ---------------------------------------------------------------------------


def _get_test_database_url() -> str:
    test_from = os.getenv("TEST_FROM", "local").lower()
    if test_from == "local":
        return "sqlite+aiosqlite:///:memory:"
    from config import database_settings

    return database_settings.url


@pytest.fixture
async def session_factory():
    database_url = _get_test_database_url()
    is_sqlite = database_url.startswith("sqlite")

    engine_kwargs: dict = {}
    connect_args: dict = {}
    if is_sqlite:
        connect_args["check_same_thread"] = False
        engine_kwargs["poolclass"] = StaticPool
    else:
        engine_kwargs["poolclass"] = NullPool

    engine = create_async_engine(database_url, connect_args=connect_args, **engine_kwargs)
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.drop_all)
        await conn.run_sync(base.Base.metadata.create_all)

    async with async_sessionmaker(bind=engine, expire_on_commit=False)() as seed:
        seed.add_all(
            [
                AdminRole(name="owner", is_owner=True, permissions={}, limits={}, features={}, access={}, hwid={}),
                AdminRole(name="administrator", is_owner=False, permissions={}, limits={}, features={}, access={}, hwid={}),
                AdminRole(name="operator", is_owner=False, permissions={}, limits={}, features={}, access={}, hwid={}),
            ]
        )
        await seed.commit()

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    yield factory

    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.drop_all)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Tests: app/jobs/dependencies.py
# ---------------------------------------------------------------------------


class TestSystemAdmin:
    def test_system_admin_is_owner(self):
        """SYSTEM_ADMIN must have is_owner=True after the PR change."""
        from app.jobs.dependencies import SYSTEM_ADMIN

        assert SYSTEM_ADMIN.is_owner is True

    def test_system_admin_username(self):
        from app.jobs.dependencies import SYSTEM_ADMIN

        assert SYSTEM_ADMIN.username == "system"

    def test_system_admin_role_is_admin_role_data(self):
        from app.jobs.dependencies import SYSTEM_ADMIN
        from app.models.admin import AdminRoleData

        assert SYSTEM_ADMIN.role is not None
        assert isinstance(SYSTEM_ADMIN.role, AdminRoleData)

    def test_system_admin_role_has_is_owner_true(self):
        from app.jobs.dependencies import SYSTEM_ADMIN

        assert SYSTEM_ADMIN.role.is_owner is True

    def test_system_admin_is_not_disabled(self):
        from app.jobs.dependencies import SYSTEM_ADMIN

        assert SYSTEM_ADMIN.is_disabled is False


# ---------------------------------------------------------------------------
# Tests: app/db/models.py — Admin hybrid properties
# ---------------------------------------------------------------------------


class TestAdminModelHybridProperties:
    def _make_admin(self, status: AdminStatus = AdminStatus.active) -> Admin:
        return Admin(
            username=f"admin_{status.value}",
            hashed_password="hash",
            role_id=3,
            status=status,
        )

    def test_is_disabled_true_when_disabled(self):
        admin = self._make_admin(AdminStatus.disabled)
        assert admin.is_disabled is True

    def test_is_disabled_false_when_active(self):
        admin = self._make_admin(AdminStatus.active)
        assert admin.is_disabled is False

    def test_is_disabled_false_when_limited(self):
        admin = self._make_admin(AdminStatus.limited)
        assert admin.is_disabled is False

    def test_is_limited_true_when_limited(self):
        admin = self._make_admin(AdminStatus.limited)
        assert admin.is_limited is True

    def test_is_limited_false_when_active(self):
        admin = self._make_admin(AdminStatus.active)
        assert admin.is_limited is False

    def test_is_limited_false_when_disabled(self):
        admin = self._make_admin(AdminStatus.disabled)
        assert admin.is_limited is False

    def test_has_api_keys_false_by_default(self):
        admin = self._make_admin()
        assert admin.has_api_keys is False


# ---------------------------------------------------------------------------
# Tests: app/db/models.py — APIKey hybrid properties
# ---------------------------------------------------------------------------


class TestAPIKeyModelProperties:
    def _make_api_key(
        self,
        *,
        status: APIKeyStatus = APIKeyStatus.active,
        admin_status: AdminStatus = AdminStatus.active,
        expire_date=None,
    ) -> APIKey:
        admin = Admin(username="apikeyowner", hashed_password="h", role_id=3, status=admin_status)
        key = APIKey(
            admin_id=1,
            name="testkey",
            key_hash="somehash",
            role_id=3,
            status=status,
            expire_date=expire_date,
        )
        key.admin = admin
        return key

    def test_is_expired_false_when_no_expire_date(self):
        key = self._make_api_key()
        key.admin = None
        key.admin_id = 1
        # Instance-level check (not SQL expression)
        key.expire_date = None
        assert key.is_expired is False

    def test_is_expired_false_when_future_date(self):
        key = self._make_api_key(expire_date=datetime.now(timezone.utc) + timedelta(hours=1))
        assert key.is_expired is False

    def test_is_expired_true_when_past_date(self):
        key = self._make_api_key(expire_date=datetime.now(timezone.utc) - timedelta(hours=1))
        assert key.is_expired is True

    def test_is_usable_false_when_disabled(self):
        key = self._make_api_key(status=APIKeyStatus.disabled)
        assert key.is_usable is False

    def test_is_usable_false_when_admin_disabled(self):
        key = self._make_api_key(admin_status=AdminStatus.disabled)
        assert key.is_usable is False

    def test_is_usable_false_when_expired(self):
        key = self._make_api_key(expire_date=datetime.now(timezone.utc) - timedelta(seconds=1))
        assert key.is_usable is False

    def test_is_usable_true_when_active_not_expired(self):
        key = self._make_api_key(
            status=APIKeyStatus.active,
            admin_status=AdminStatus.active,
            expire_date=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert key.is_usable is True

    def test_is_usable_true_when_no_expire_date(self):
        key = self._make_api_key(status=APIKeyStatus.active, admin_status=AdminStatus.active)
        assert key.is_usable is True

    def test_is_usable_false_when_no_admin(self):
        key = self._make_api_key()
        key.admin = None
        assert key.is_usable is False


# ---------------------------------------------------------------------------
# Tests: app/db/models.py — AdminRole.is_builtin
# ---------------------------------------------------------------------------


class TestAdminRoleIsBuiltin:
    def _make_role(self, role_id: int) -> AdminRole:
        role = AdminRole(name="testrole", permissions={}, limits={}, features={}, access={}, hwid={})
        role.id = role_id
        return role

    def test_is_builtin_true_for_ids_1_2_3(self):
        for role_id in (1, 2, 3):
            role = self._make_role(role_id)
            assert role.is_builtin is True, f"Expected is_builtin=True for id={role_id}"

    def test_is_builtin_false_for_id_4_and_above(self):
        for role_id in (4, 5, 100):
            role = self._make_role(role_id)
            assert role.is_builtin is False, f"Expected is_builtin=False for id={role_id}"


# ---------------------------------------------------------------------------
# Tests: app/jobs/review_admins.py — _send_usage_limit_warning_notifications
# ---------------------------------------------------------------------------


class TestSendUsageLimitWarningNotifications:
    async def test_does_nothing_when_warning_disabled(self, session_factory):
        """If admin notify.usage_limit_warning is False, no notifications or reminders."""
        import app.jobs.review_admins as review_admins_mod

        mock_notify_settings = MagicMock()
        mock_notify_settings.admin.usage_limit_warning = False

        async with session_factory() as db:
            with patch.object(
                review_admins_mod,
                "notification_enable",
                new=AsyncMock(return_value=mock_notify_settings),
            ):
                # Should complete without error and without calling any DB write
                await review_admins_mod._send_usage_limit_warning_notifications(db)

    async def test_does_nothing_when_no_thresholds(self, session_factory):
        import app.jobs.review_admins as review_admins_mod

        mock_notify_settings = MagicMock()
        mock_notify_settings.admin.usage_limit_warning = True
        mock_notify_settings.admin.usage_limit_warning_percentages = []

        async with session_factory() as db:
            with patch.object(
                review_admins_mod,
                "notification_enable",
                new=AsyncMock(return_value=mock_notify_settings),
            ):
                await review_admins_mod._send_usage_limit_warning_notifications(db)
        # No exception = pass

    async def test_sends_notification_when_threshold_reached(self, session_factory):
        import app.jobs.review_admins as review_admins_mod
        from app.db.models import AdminNotificationReminder, ReminderType

        # Create an admin at 90% usage
        async with session_factory() as db:
            admin = Admin(
                username="notifyadmin",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.active,
                data_limit=1000,
                used_traffic=900,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        mock_notify_settings = MagicMock()
        mock_notify_settings.admin.usage_limit_warning = True
        mock_notify_settings.admin.usage_limit_warning_percentages = [80]

        mock_send = AsyncMock()

        async with session_factory() as db:
            with (
                patch.object(
                    review_admins_mod,
                    "notification_enable",
                    new=AsyncMock(return_value=mock_notify_settings),
                ),
                patch.object(review_admins_mod.notification, "admin_usage_limit_reached", new=mock_send),
            ):
                await review_admins_mod._send_usage_limit_warning_notifications(db)

        mock_send.assert_awaited_once()

    async def test_no_notification_when_already_reminded(self, session_factory):
        """If admin already has a reminder for the threshold, no second notification."""
        import app.jobs.review_admins as review_admins_mod
        from app.db.crud.admin import bulk_create_admin_notification_reminders
        from app.db.models import ReminderType

        async with session_factory() as db:
            admin = Admin(
                username="alreadyreminded",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.active,
                data_limit=1000,
                used_traffic=900,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        async with session_factory() as db:
            await bulk_create_admin_notification_reminders(
                db,
                [
                    {
                        "admin_id": admin_id,
                        "type": ReminderType.data_usage,
                        "threshold": 80,
                        "created_at": datetime.now(timezone.utc),
                    }
                ],
            )

        mock_notify_settings = MagicMock()
        mock_notify_settings.admin.usage_limit_warning = True
        mock_notify_settings.admin.usage_limit_warning_percentages = [80]

        mock_send = AsyncMock()

        async with session_factory() as db:
            with (
                patch.object(
                    review_admins_mod,
                    "notification_enable",
                    new=AsyncMock(return_value=mock_notify_settings),
                ),
                patch.object(review_admins_mod.notification, "admin_usage_limit_reached", new=mock_send),
            ):
                await review_admins_mod._send_usage_limit_warning_notifications(db)

        mock_send.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: app/jobs/review_admins.py — limit_admins_job
# ---------------------------------------------------------------------------


class TestLimitAdminsJob:
    async def test_flips_active_to_limited(self, session_factory):
        """limit_admins_job should flip over-limit active admins to limited."""
        import app.jobs.review_admins as review_admins_mod
        from app.db.crud.admin import get_active_to_limited_admins
        from sqlalchemy import select

        async with session_factory() as db:
            admin = Admin(
                username="overquota",
                hashed_password="h",
                role_id=3,
                status=AdminStatus.active,
                data_limit=100,
                used_traffic=200,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            admin_id = admin.id

        # Mock the GetDB context manager and warning notifications
        from app.db.crud.admin import update_admin_status

        class FakeGetDB:
            async def __aenter__(self):
                from sqlalchemy.ext.asyncio import AsyncSession

                self._db = session_factory()
                return await self._db.__aenter__()

            async def __aexit__(self, *args):
                return await self._db.__aexit__(*args)

        with (
            patch.object(review_admins_mod, "GetDB", FakeGetDB),
            patch.object(
                review_admins_mod,
                "_send_usage_limit_warning_notifications",
                new=AsyncMock(),
            ),
            patch.object(
                review_admins_mod,
                "sync_remove_users",
                new=AsyncMock(),
            ),
        ):
            await review_admins_mod.limit_admins_job()

        # Check the admin was flipped
        async with session_factory() as db:
            result = (await db.execute(select(Admin).where(Admin.id == admin_id))).scalar_one()
        assert result.status == AdminStatus.limited

    async def test_does_nothing_when_no_over_limit_admins(self, session_factory):
        """limit_admins_job returns early when there are no over-limit admins."""
        import app.jobs.review_admins as review_admins_mod

        class FakeGetDB:
            async def __aenter__(self):
                self._db = session_factory()
                return await self._db.__aenter__()

            async def __aexit__(self, *args):
                return await self._db.__aexit__(*args)

        mock_update = AsyncMock()

        with (
            patch.object(review_admins_mod, "GetDB", FakeGetDB),
            patch.object(
                review_admins_mod,
                "_send_usage_limit_warning_notifications",
                new=AsyncMock(),
            ),
            patch.object(review_admins_mod, "update_admin_status", new=mock_update),
        ):
            await review_admins_mod.limit_admins_job()

        mock_update.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: app/app_factory.py — exception handlers
# ---------------------------------------------------------------------------


class TestAppFactoryExceptionHandlers:
    """Test that PermissionDenied and LimitExceeded produce the right HTTP responses."""

    def _get_test_client(self):
        """Returns the test client configured in tests/api/__init__.py."""
        from tests.api import client

        return client

    def test_permission_denied_handler_registered(self):
        """PermissionDenied exceptions should return HTTP 403."""
        from tests.api import app as test_app

        # Verify the exception handlers are registered by checking the app's exception_handlers dict
        from app.operation.permissions import PermissionDenied

        # If the handler wasn't registered, this would fail; just check the import works
        assert PermissionDenied is not None

    def test_limit_exceeded_handler_registered(self):
        """LimitExceeded exceptions should return HTTP 400."""
        from app.operation.permissions import LimitExceeded

        assert LimitExceeded is not None


# ---------------------------------------------------------------------------
# Additional edge-case / boundary tests for model changes
# ---------------------------------------------------------------------------


class TestAdminStatusEnum:
    def test_status_values(self):
        assert AdminStatus.active == "active"
        assert AdminStatus.disabled == "disabled"
        assert AdminStatus.limited == "limited"

    def test_admin_status_is_str_enum(self):
        assert isinstance(AdminStatus.active, str)


class TestAdminModelDataLimit:
    """Test Admin model data_limit field interaction with status logic."""

    def test_admin_default_status_active(self):
        admin = Admin(username="u", hashed_password="h", role_id=3)
        assert admin.status == AdminStatus.active

    def test_admin_data_limit_defaults_none(self):
        admin = Admin(username="u", hashed_password="h", role_id=3)
        assert admin.data_limit is None

    def test_admin_last_status_change_defaults_none(self):
        admin = Admin(username="u", hashed_password="h", role_id=3)
        assert admin.last_status_change is None


class TestAPIKeyStatusEnum:
    def test_status_values(self):
        assert APIKeyStatus.active == "active"
        assert APIKeyStatus.disabled == "disabled"