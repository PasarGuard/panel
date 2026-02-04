import asyncio
from datetime import timedelta

from app import __version__
from app.core.manager import core_manager
from app.db import AsyncSession
from app.db.crud.admin import get_admin
from app.db.crud.general import get_system_usage
from app.db.crud.user import count_online_users, get_users_count_by_status
from app.db.models import UserStatus
from app.models.admin import AdminDetails
from app.models.system import SystemStats
from app.utils.system import cpu_usage, memory_usage

from . import BaseOperation


class SystemOperation(BaseOperation):
    @staticmethod
    async def get_system_stats(db: AsyncSession, admin: AdminDetails, admin_username: str | None = None) -> SystemStats:
        """Fetch system stats including memory, CPU, and user metrics."""
        # Run sync functions off the event loop
        mem_task = asyncio.to_thread(memory_usage)
        cpu_task = asyncio.to_thread(cpu_usage)

        admin_param = None
        if admin.is_sudo and admin_username:
            admin_param = await get_admin(db, admin_username)
        elif not admin.is_sudo:
            admin_param = admin

        system_task = None
        if not admin_param:
            system_task = get_system_usage(db)

        admin_id = admin_param.id if admin_param else None

        # Get user counts by status in a single query and online users count
        statuses = [UserStatus.active, UserStatus.disabled, UserStatus.on_hold, UserStatus.expired, UserStatus.limited]
        user_counts_task = get_users_count_by_status(db, statuses, admin_id)
        online_users_task = count_online_users(db, timedelta(minutes=2), admin_id)

        tasks = [mem_task, cpu_task, user_counts_task, online_users_task]
        if system_task is not None:
            tasks.append(system_task)

        results = await asyncio.gather(*tasks)

        mem = results[0]
        cpu = results[1]
        user_counts = results[2]
        online_users = results[3]

        if system_task is not None:
            system = results[4]
            uplink = system.uplink
            downlink = system.downlink
        else:
            uplink = 0
            downlink = admin_param.used_traffic

        return SystemStats(
            version=__version__,
            mem_total=mem.total,
            mem_used=mem.used,
            cpu_cores=cpu.cores,
            cpu_usage=cpu.percent,
            total_user=user_counts["total"],
            online_users=online_users,
            active_users=user_counts[UserStatus.active.value],
            disabled_users=user_counts[UserStatus.disabled.value],
            expired_users=user_counts[UserStatus.expired.value],
            limited_users=user_counts[UserStatus.limited.value],
            on_hold_users=user_counts[UserStatus.on_hold.value],
            incoming_bandwidth=uplink,
            outgoing_bandwidth=downlink,
        )

    @staticmethod
    async def get_inbounds() -> list[str]:
        return await core_manager.get_inbounds()
