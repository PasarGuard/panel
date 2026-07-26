import pytest
from uuid import uuid4
from sqlalchemy import select
from app.db.models import Admin, AdminNotificationReminder, AdminRole, ReminderType
from app.db.crud.admin import bulk_create_admin_notification_reminders
from app.jobs.review_admins import _send_usage_limit_warning_notifications
from tests.api import TestSession, engine
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture(autouse=True)
async def setup_database():
    from app.db import base
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.create_all)
        
    async with TestSession() as session:
        # Seed default roles if they do not exist (to satisfy FK constraints)
        existing_roles = (await session.execute(select(AdminRole))).scalars().all()
        if not existing_roles:
            session.add_all(
                [
                    AdminRole(id=1, name="owner", is_owner=True, permissions={}, limits={}, features={}, access={}),
                    AdminRole(id=2, name="administrator", is_owner=False, permissions={}, limits={}, features={}, access={}),
                    AdminRole(id=3, name="operator", is_owner=False, permissions={}, limits={}, features={}, access={}),
                ]
            )
            await session.commit()

@pytest.mark.asyncio
async def test_bulk_create_admin_notification_reminders_idempotency():
    async with TestSession() as session:
        # Create an admin to associate reminders with
        admin = Admin(username=f"idempotent_{uuid4().hex[:8]}", hashed_password="secret", role_id=3)
        session.add(admin)
        await session.flush()
        
        reminder_data = [
            {"admin_id": admin.id, "type": ReminderType.data_usage, "threshold": 80},
            {"admin_id": admin.id, "type": ReminderType.data_usage, "threshold": 80}, # duplicate input
        ]
        
        # Call the bulk helper
        inserted = await bulk_create_admin_notification_reminders(session, reminder_data)
        
        # Check that only one was inserted and returned
        assert len(inserted) == 1
        assert inserted[0]["admin_id"] == admin.id
        assert inserted[0]["threshold"] == 80
        
        # Query DB to verify
        db_reminders = (await session.execute(
            select(AdminNotificationReminder).where(AdminNotificationReminder.admin_id == admin.id)
        )).scalars().all()
        assert len(db_reminders) == 1
        assert db_reminders[0].threshold == 80
        
        # Run again with same data
        inserted_second = await bulk_create_admin_notification_reminders(session, reminder_data)
        assert len(inserted_second) == 0
        
        # DB count should still be 1
        db_reminders_second = (await session.execute(
            select(AdminNotificationReminder).where(AdminNotificationReminder.admin_id == admin.id)
        )).scalars().all()
        assert len(db_reminders_second) == 1

@pytest.mark.asyncio
@patch("app.jobs.review_admins.notification")
@patch("app.jobs.review_admins.notification_enable")
@patch("app.jobs.review_admins.get_usage_percentage_reached_admins")
@patch("app.jobs.review_admins._admin_usage_warning_details")
async def test_send_usage_limit_warning_notifications_idempotent(
    mock_details, mock_get_admins, mock_notif_enable, mock_notification
):
    async with TestSession() as session:
        # Create test admin
        admin = Admin(
            username=f"notif_{uuid4().hex[:8]}",
            hashed_password="secret",
            role_id=3,
            data_limit=1000,
            used_traffic=850, # 85% usage
        )
        session.add(admin)
        await session.flush()
        
        # Setup mocks
        mock_details.return_value = MagicMock()
        
        mock_notif_enable.return_value = AsyncMock()
        mock_notif_enable.return_value.admin.usage_limit_warning = True
        mock_notif_enable.return_value.admin.usage_limit_warning_percentages = [80]
        
        mock_get_admins.return_value = [admin]
        
        mock_notification.admin_usage_limit_reached = AsyncMock()
        
        # First call: should insert reminder and send notification
        await _send_usage_limit_warning_notifications(session)
        assert mock_notification.admin_usage_limit_reached.call_count == 1
        
        # Reset mock
        mock_notification.admin_usage_limit_reached.reset_mock()
        
        # Second call: should NOT send notification (since reminder exists)
        await _send_usage_limit_warning_notifications(session)
        assert mock_notification.admin_usage_limit_reached.call_count == 0

@pytest.mark.asyncio
@patch("app.jobs.review_admins.notification")
@patch("app.jobs.review_admins.notification_enable")
@patch("app.jobs.review_admins.get_usage_percentage_reached_admins")
@patch("app.jobs.review_admins._admin_usage_warning_details")
async def test_send_usage_limit_warning_notifications_failure_handling(
    mock_details, mock_get_admins, mock_notif_enable, mock_notification
):
    async with TestSession() as session:
        # Create test admins
        admin_ok = Admin(
            username=f"ok_{uuid4().hex[:8]}",
            hashed_password="secret",
            role_id=3,
            data_limit=1000,
            used_traffic=850,
        )
        admin_fail = Admin(
            username=f"fail_{uuid4().hex[:8]}",
            hashed_password="secret",
            role_id=3,
            data_limit=1000,
            used_traffic=850,
        )
        session.add_all([admin_ok, admin_fail])
        await session.flush()

        mock_details.side_effect = lambda admin: MagicMock(id=admin.id)

        mock_notif_enable.return_value = AsyncMock()
        mock_notif_enable.return_value.admin.usage_limit_warning = True
        mock_notif_enable.return_value.admin.usage_limit_warning_percentages = [80]

        mock_get_admins.return_value = [admin_ok, admin_fail]

        # Succeed for admin_ok, raise exception for admin_fail
        async def side_effect(admin_model, usage_percentage, threshold):
            if admin_model.id == admin_fail.id:
                raise RuntimeError("Network failure")
            return

        mock_notification.admin_usage_limit_reached = AsyncMock(side_effect=side_effect)

        # Call notifications
        await _send_usage_limit_warning_notifications(session)

        # Query DB to verify reminders
        reminders = (await session.execute(
            select(AdminNotificationReminder)
        )).scalars().all()

        admin_ids_with_reminders = {r.admin_id for r in reminders}
        assert admin_ok.id in admin_ids_with_reminders
        assert admin_fail.id not in admin_ids_with_reminders
