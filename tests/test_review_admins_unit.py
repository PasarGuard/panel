import pytest
from sqlalchemy import select
from app.db.models import Admin, AdminNotificationReminder, ReminderType
from app.db.crud.admin import bulk_create_admin_notification_reminders
from app.jobs.review_admins import _send_usage_limit_warning_notifications
from tests.api import TestSession
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_bulk_create_admin_notification_reminders_idempotency():
    async with TestSession() as session:
        # Create an admin to associate reminders with
        admin = Admin(username="idempotent_admin", hashed_password="secret", role_id=3)
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
            username="notif_admin",
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
