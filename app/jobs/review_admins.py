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
    bulk_create_admin_notification_reminders,
    get_active_admins_with_data_limit,
    get_active_admins_with_override_thresholds,
    get_active_to_limited_admins,
    get_admin_usage_reminder_thresholds,
    update_admin_status,
)
from app.db.crud.user import get_users
from app.db.models import Admin, AdminStatus, ReminderType, UserStatus
from app.models.admin import AdminDetails
from app.models.user import UserListQuery
from app.models.validators import ListValidator
from app.node.sync import remove_users as sync_remove_users
from app.settings import notification_enable
from app.utils.logger import get_logger
from config import job_settings, runtime_settings

logger = get_logger("review-admins")


def _get_effective_admin_thresholds(admin: Admin, default_thresholds: list[int]) -> list[int]:
    overrides = admin.permission_overrides or {}
    override_values = overrides.get("usage_limit_warning_percentages") if isinstance(overrides, dict) else None

    if override_values is None:
        return default_thresholds
    thresholds = ListValidator.normalize_percentage_list_input(override_values, strict=False)
    return thresholds or []


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

    override_admins = await get_active_admins_with_override_thresholds(db)
    override_thresholds_by_admin: dict[int, list[int]] = {}
    threshold_to_override_ids: dict[int, set[int]] = {}

    for admin in override_admins:
        thresholds = _get_effective_admin_thresholds(admin, default_thresholds)
        if not thresholds:
            continue
        override_thresholds_by_admin[admin.id] = thresholds
        for threshold in thresholds:
            threshold_to_override_ids.setdefault(threshold, set()).add(admin.id)

    override_ids = set(override_thresholds_by_admin.keys())
    candidate_pairs: dict[tuple[int, int], Admin] = {}

    for threshold in default_thresholds:
        threshold_admins = await get_active_admins_with_data_limit(db, threshold=threshold)
        for admin in threshold_admins:
            if admin.id in override_ids:
                continue
            candidate_pairs[(admin.id, threshold)] = admin

    for threshold, admin_ids in threshold_to_override_ids.items():
        threshold_admins = await get_active_admins_with_data_limit(db, threshold=threshold, admin_ids=list(admin_ids))
        for admin in threshold_admins:
            candidate_pairs[(admin.id, threshold)] = admin

    if not candidate_pairs:
        return

    candidate_admin_ids = sorted({admin_id for admin_id, _ in candidate_pairs.keys()})
    already_sent = await get_admin_usage_reminder_thresholds(db, candidate_admin_ids, ReminderType.data_usage)
    reminder_rows: list[dict] = []

    for (admin_id, threshold), admin in candidate_pairs.items():
        if threshold in already_sent.get(admin_id, set()):
            continue

        if not admin.data_limit or admin.data_limit <= 0:
            continue

        usage_percentage = int((admin.used_traffic * 100) / admin.data_limit)
        admin_model = AdminDetails.model_validate(admin)
        await notification.admin_usage_limit_reached(admin_model, usage_percentage, threshold)
        reminder_rows.append({
            "admin_id": admin.id,
            "type": ReminderType.data_usage,
            "threshold": threshold,
        })

    if reminder_rows:
        await bulk_create_admin_notification_reminders(db, reminder_rows)


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

            if admin.role and admin.role.disable_users_when_limited:
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
