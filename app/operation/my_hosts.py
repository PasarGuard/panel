from fastapi import HTTPException

from app.db import AsyncSession
from app.db.base import begin_immediate_if_sqlite
from app.db.crud.my_hosts import get_personal_hosts, get_preferences_admin
from app.models.admin import AdminDetails
from app.models.my_hosts import HostPreference, MyHost, MyHostsPolicy, MyHostsResponse, MyHostsUpdate
from app.operation.permissions import get_allowed_group_ids
from app.settings import general_settings
from app.utils.logger import get_logger

logger = get_logger("my-hosts")


async def get_policy() -> MyHostsPolicy:
    return (await general_settings()).my_hosts or MyHostsPolicy()


def check_access(admin: AdminDetails, policy: MyHostsPolicy, *, write: bool = False):
    if not policy.enabled:
        raise HTTPException(403, "My Hosts is disabled by the owner")
    if not admin.id:
        raise HTTPException(403, "My Hosts requires a database admin account")
    if admin.is_limited and (write or (admin.role and admin.role.disabled_when_limited)):
        raise HTTPException(403, "My Hosts access is restricted while your account is limited")


def check_changes(old: HostPreference, patch: dict, policy: MyHostsPolicy):
    for field, allowed in (
        ("remark", policy.allow_rename),
        ("position", policy.allow_reorder),
        ("is_disabled", policy.allow_disable),
    ):
        if field in patch and patch[field] != getattr(old, field) and not allowed:
            raise HTTPException(403, f"My Hosts operation is not allowed: {field}")


class MyHostsOperation:
    async def get_hosts(self, db: AsyncSession, admin: AdminDetails) -> MyHostsResponse:
        policy = await get_policy()
        check_access(admin, policy)
        db_admin = await get_preferences_admin(db, admin.id)
        if db_admin is None:
            raise HTTPException(404, "Admin not found")
        preferences = db_admin.host_preferences or {}
        hosts = await get_personal_hosts(db, get_allowed_group_ids(admin))
        default_positions = {host.id: index for index, host in enumerate(hosts)}
        if policy.allow_reorder:
            hosts.sort(
                key=lambda host: (
                    HostPreference.model_validate(preferences.get(str(host.id), {})).position is None,
                    HostPreference.model_validate(preferences.get(str(host.id), {})).position or 0,
                )
            )
        result = []
        for host in hosts:
            preference = HostPreference.model_validate(preferences.get(str(host.id), {}))
            result.append(
                MyHost(
                    id=host.id,
                    default_position=default_positions[host.id],
                    original_remark=host.remark,
                    inbound_tag=host.inbound_tag,
                    remark=(preference.remark if policy.allow_rename else None) or host.remark,
                    is_disabled=bool(host.is_disabled) or (policy.allow_disable and preference.is_disabled),
                    globally_disabled=bool(host.is_disabled),
                    preference=preference,
                )
            )
        return MyHostsResponse(policy=policy, hosts=result)

    async def modify_hosts(self, db: AsyncSession, admin: AdminDetails, update: MyHostsUpdate) -> MyHostsResponse:
        policy = await get_policy()
        check_access(admin, policy, write=True)
        await begin_immediate_if_sqlite(db)
        db_admin = await get_preferences_admin(db, admin.id, lock=True)
        if db_admin is None:
            raise HTTPException(404, "Admin not found")
        available = {host.id for host in await get_personal_hosts(db, get_allowed_group_ids(admin))}
        preferences = dict(db_admin.host_preferences or {})
        for host in update.hosts:
            if host.id not in available:
                raise HTTPException(404, "Host not found")
            key = str(host.id)
            old = HostPreference.model_validate(preferences.get(key, {}))
            patch = host.model_dump(exclude_unset=True, exclude={"id"})
            check_changes(old, patch, policy)
            new = HostPreference.model_validate(old.model_dump() | patch)
            if new == HostPreference():
                preferences.pop(key, None)
            else:
                preferences[key] = new.model_dump()
        db_admin.host_preferences = preferences or None
        await db.commit()
        logger.info('Admin "%s" updated personal preferences for %d hosts', admin.username, len(update.hosts))
        return await self.get_hosts(db, admin)
