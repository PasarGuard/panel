"""
Review admin data limits and flip active → limited for admins that exceeded their data_limit.

The reverse (limited → active) happens synchronously in the operation layer:
- _modify_admin: when data_limit is raised or cleared
- _reset_admin_usage: when used_traffic is zeroed

This job only handles the active → limited transition that occurs via traffic accumulation
(record_usages increments used_traffic but doesn't load admin objects).
"""

from datetime import datetime as dt, timezone as tz

from app import scheduler
from app.db import GetDB
from app.db.crud.admin import get_active_to_limited_admins, update_admin_status
from app.db.crud.user import get_users
from app.db.models import AdminStatus, UserStatus
from app.models.user import UserListQuery
from app.node.sync import remove_users as sync_remove_users
from app.utils.logger import get_logger
from config import job_settings, runtime_settings

logger = get_logger("review-admins")


async def limit_admins_job():
    """Flip active → limited for admins that exceeded their data_limit and remove their users from nodes."""
    async with GetDB() as db:
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
