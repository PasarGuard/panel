"""
Review admin data limits and flip active admins to limited when they exceed data_limit.

The reverse transition happens synchronously in the operation layer:
- _modify_admin: when data_limit is raised or cleared
- _reset_admin_usage: when used_traffic is zeroed

record_usages increments used_traffic without loading admin objects, so this job
handles the active to limited transition and removes affected users from nodes.
"""

from datetime import UTC, datetime as dt

from sqlalchemy import select

from app import notification, scheduler
from app.db import GetDB
from app.db.crud.admin import (
    bulk_create_admin_notification_reminders,
    get_usage_percentage_reached_admins,
)
from app.db.models import Admin, AdminNotificationReminder, ReminderType
from app.models.admin import AdminDetails, AdminRoleData
from app.models.admin_role import RoleLimits
from app.models.validators import ListValidator
from app.operation.admin_sync import limit_exceeded_admins
from app.settings import notification_enable
from app.utils.logger import get_logger
from config import job_settings, runtime_settings

logger = get_logger("review-admins")


def _admin_usage_warning_details(admin: Admin) -> AdminDetails:
    return AdminDetails(
        id=admin.id,
        username=admin.username,
        used_traffic=int(admin.used_traffic or 0),
        data_limit=admin.data_limit,
        status=admin.status,
        telegram_id=admin.telegram_id,
        discord_webhook=admin.discord_webhook,
        sub_domain=admin.sub_domain,
        profile_title=admin.profile_title,
        support_url=admin.support_url,
        custom_variables=admin.custom_variables or [],
        notification_enable=admin.notification_enable,
        sub_template=admin.sub_template,
        note=admin.note,
        role=AdminRoleData.model_validate(admin.role) if admin.role else None,
        permission_overrides=RoleLimits.model_validate(admin.permission_overrides)
        if admin.permission_overrides
        else None,
    )


async def _send_usage_limit_warning_notifications(db):
    notify_settings = await notification_enable()
    admin_notify = notify_settings.admin

    if not admin_notify.usage_limit_warning:
        return

    default_thresholds = ListValidator.normalize_percentage_list_input(
        admin_notify.usage_limit_warning_percentages,
        strict=False,
    )
    default_thresholds = default_thresholds or []
    if not default_thresholds:
        return

    for threshold in default_thresholds:
        threshold_admins = await get_usage_percentage_reached_admins(db, threshold)

        candidate_admins = [admin for admin in threshold_admins if admin.data_limit and admin.data_limit > 0]
        if not candidate_admins:
            continue

        candidate_ids = [admin.id for admin in candidate_admins]

        # Lock the Admin rows to serialize reminder checks/creation for these admins
        await db.execute(
            select(Admin.id)
            .where(Admin.id.in_(candidate_ids))
            .with_for_update()
        )

        # Fetch existing reminders for this threshold to avoid duplicate notifications
        result = await db.execute(
            select(AdminNotificationReminder.admin_id)
            .where(
                AdminNotificationReminder.admin_id.in_(candidate_ids),
                AdminNotificationReminder.type == ReminderType.data_usage,
                AdminNotificationReminder.threshold == threshold,
            )
        )
        existing_ids = set(result.scalars().all())

        successfully_sent = []
        for admin in candidate_admins:
            if admin.id in existing_ids:
                continue

            usage_percentage = int((admin.used_traffic * 100) / admin.data_limit)
            admin_model = _admin_usage_warning_details(admin)

            try:
                # Send the notification first
                await notification.admin_usage_limit_reached(admin_model, usage_percentage, threshold)
                successfully_sent.append(
                    {"admin_id": admin.id, "type": ReminderType.data_usage, "threshold": threshold}
                )
            except Exception as e:
                logger.error(f"Failed to send usage limit warning to admin {admin.id}: {e}")

        # Bulk-insert only successfully sent reminders after sending
        if successfully_sent:
            await bulk_create_admin_notification_reminders(db, successfully_sent)


async def limit_admins_job():
    """Send warning notifications and flip active admins to limited when they exceed data_limit."""
    async with GetDB() as db:
        await _send_usage_limit_warning_notifications(db)
        await limit_exceeded_admins(db, logger=logger)


if runtime_settings.role.runs_scheduler:
    scheduler.add_job(
        limit_admins_job,
        "interval",
        seconds=job_settings.review_admin_limits_interval,
        coalesce=True,
        max_instances=1,
        start_date=dt.now(UTC),
        id="limit_admins",
        replace_existing=True,
    )
