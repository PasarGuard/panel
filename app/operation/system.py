import asyncio
from datetime import timedelta

from app import __version__
from app.core.manager import core_manager
from app.db import AsyncSession
from app.db.crud.admin import build_admin_details, get_admin
from app.db.crud.general import get_system_usage
from app.db.crud.user import count_online_users, get_users_count_by_status
from app.db.models import UserStatus
from app.models.admin import AdminDetails
from app.models.system import InboundSummary, SystemResourceStats, SystemStats, SystemUsersStats
from app.operation.permissions import PermissionDenied, enforce_permission, is_scope_all
from app.utils.system import cpu_usage, disk_usage, get_uptime, memory_usage

from . import BaseOperation


class SystemOperation(BaseOperation):
    @staticmethod
    async def get_system_resource_stats() -> SystemResourceStats:
        """Fetch system resource stats without user metrics."""
        mem_task = asyncio.create_task(asyncio.to_thread(memory_usage))
        cpu_task = asyncio.create_task(asyncio.to_thread(cpu_usage))
        disk_task = asyncio.create_task(asyncio.to_thread(disk_usage))
        uptime_task = asyncio.create_task(asyncio.to_thread(get_uptime))

        mem, cpu, disk, uptime_seconds = await asyncio.gather(mem_task, cpu_task, disk_task, uptime_task)

        return SystemResourceStats(
            version=__version__,
            uptime_seconds=uptime_seconds,
            mem_total=mem.total,
            mem_used=mem.used,
            disk_total=disk.total,
            disk_used=disk.used,
            cpu_cores=cpu.cores,
            cpu_usage=cpu.percent,
        )

    @staticmethod
    async def get_system_users_stats(
        db: AsyncSession, admin: AdminDetails, admin_username: str | None = None
    ) -> SystemUsersStats:
        """Fetch user counts and traffic metrics, scoped to the requesting admin."""
        # Determine which admin's stats to show:
        # - Owner with no admin_username: global system stats (all users)
        # - Owner with admin_username: that admin's stats
        # - Non-owner with admins.read + admin_username: that admin's stats
        # - Non-owner (any other case): scoped to their own users only
        admin_param: AdminDetails | None = None
        if admin_username:
            can_read_admins = False
            if not admin.is_owner:
                try:
                    enforce_permission(admin, "admins", "read")
                    can_read_admins = True
                except PermissionDenied:
                    can_read_admins = False
            if admin.is_owner or can_read_admins:
                db_admin = await get_admin(db, admin_username, load_users=False, load_usage_logs=False)
                if db_admin is not None:
                    admin_param = build_admin_details(db_admin)
            else:
                admin_param = admin
        elif not admin.is_owner:
            if not is_scope_all(admin, "users", "read"):
                admin_param = admin

        system_task = None
        if not admin_param:
            system_task = get_system_usage(db)

        admin_id = admin_param.id if admin_param else None

        statuses = [UserStatus.active, UserStatus.disabled, UserStatus.on_hold, UserStatus.expired, UserStatus.limited]
        if system_task is not None:
            system = await system_task
        else:
            system = None

        user_counts = await get_users_count_by_status(db, statuses, admin_id)
        online_users = await count_online_users(db, timedelta(minutes=2), admin_id)

        if system is not None:
            uplink = system.uplink
            downlink = system.downlink
        else:
            uplink = 0
            downlink = admin_param.used_traffic

        return SystemUsersStats(
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
    async def get_system_stats(db: AsyncSession, admin: AdminDetails, admin_username: str | None = None) -> SystemStats:
        """Fetch system stats including memory, CPU, disk, and user metrics."""
        resource_stats, users_stats = await asyncio.gather(
            SystemOperation.get_system_resource_stats(),
            SystemOperation.get_system_users_stats(db, admin=admin, admin_username=admin_username),
        )
        return SystemStats(**resource_stats.model_dump(), **users_stats.model_dump())

    @staticmethod
    async def get_inbounds() -> list[str]:
        return await core_manager.get_inbounds()

    @staticmethod
    async def get_inbound_details() -> list[InboundSummary]:
        inbounds = await core_manager.get_inbounds_by_tag()
        summaries: list[InboundSummary] = []
        for tag, data in sorted(inbounds.items()):
            protocol = data.get("protocol", "")
            kwargs: dict = {"tag": tag, "protocol": protocol, "network": data.get("network")}
            if protocol == "wireguard":
                addrs = data.get("address")
                kwargs["wireguard_public_key"] = data.get("public_key") or None
                kwargs["wireguard_private_key"] = data.get("private_key") or None
                kwargs["wireguard_pre_shared_key"] = data.get("pre_shared_key") or None
                kwargs["wireguard_listen_port"] = data.get("listen_port")
                kwargs["wireguard_addresses"] = list(addrs) if isinstance(addrs, list) else None
            summaries.append(InboundSummary(**kwargs))
        return summaries
