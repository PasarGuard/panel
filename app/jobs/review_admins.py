"""
Review admin data limits and flip active → limited for admins that exceeded their data_limit.

The reverse (limited → active) happens synchronously in the operation layer:
- _modify_admin: when data_limit is raised or cleared
- _reset_admin_usage: when used_traffic is zeroed

This job only handles the active → limited transition that occurs via traffic accumulation
(record_usages increments used_traffic but doesn't load admin objects).
"""

from datetime import datetime as dt, timezone as tz

from app import notification, scheduler
from app.db import GetDB
from app.db.crud.admin import (
    create_admin_notification_reminder_if_absent,
    get_active_to_limited_admins,
    get_usage_percentage_reached_admins,
    update_admin_status,
)
from app.db.crud.user import get_users
from app.db.models import Admin, AdminStatus, ReminderType, UserStatus
from app.models.admin import AdminDetails, AdminRoleData
from app.models.admin_role import RoleLimits
from app.models.user import UserListQuery
from app.models.validators import ListValidator
from app.node.sync import remove_users as sync_remove_users
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
        for admin in threshold_admins:
            if not admin.data_limit or admin.data_limit <= 0:
                continue
            reminder_created = await create_admin_notification_reminder_if_absent(
                db,
                admin.id,
                ReminderType.data_usage,
                threshold,
            )
            if not reminder_created:
                continue
            usage_percentage = int((admin.used_traffic * 100) / admin.data_limit)
            admin_model = _admin_usage_warning_details(admin)
            await notification.admin_usage_limit_reached(admin_model, usage_percentage, threshold)


async def limit_admins_job():
    """Send warning notifications and flip active → limited admins that exceeded data_limit."""
    async with GetDB() as db:
        await _send_usage_limit_warning_notifications(db)

        admins = await get_active_to_limited_admins(db)
        if not admins:
            return

        for admin in admins:
            await update_admin_status(db, admin, AdminStatus.limited)
            logger.info(f'Admin "{admin.username}" status changed to limited')

            if admin.role and admin.role.disconnect_users_when_limited:
                users = await get_users(
                    db,
                    query=UserListQuery(status=[UserStatus.active, UserStatus.on_hold]),
                    admin=admin,
                )
                await sync_remove_users(users)
                logger.info(f'Admin "{admin.username}" — removed {len(users)} users from nodes')


if runtime_settings.role.runs_scheduler:
    scheduler.add_job(
        limit_admins_job,
        "interval",
        seconds=job_settings.review_admin_limits_interval,
        coalesce=True,
        max_instances=1,
        start_date=dt.now(tz.utc),
        id="limit_admins",
        replace_existing=True,
    )
