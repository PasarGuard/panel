from __future__ import annotations

import json
from ipaddress import ip_network
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.manager import core_manager
from app.db.crud.user import get_all_wireguard_peer_ips_raw
from app.db.models import CoreConfig, CoreType, User
from app.models.proxy import ProxyTable
from app.node.sync import sync_users
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key
from app.utils.ip_pool import (
    WireGuardPeerIPAllocator,
    allocate_and_validate_peer_ips,
    collect_used_peer_networks_from_proxy_settings_rows,
    peer_ips_outside_global_pool,
)


def _normalized_peer_networks(peer_ips: Iterable[str]) -> list[str]:
    networks: list[str] = []
    for peer_ip in peer_ips:
        try:
            networks.append(str(ip_network(peer_ip, strict=False)))
        except ValueError:
            continue
    return networks


def _peer_network_owners_from_rows(rows: Iterable[dict]) -> dict[str, set[int]]:
    owners: dict[str, set[int]] = {}
    for row in rows:
        uid = row.get("id")
        if uid is None:
            continue
        proxy_settings = row.get("proxy_settings") or {}
        if isinstance(proxy_settings, str):
            proxy_settings = json.loads(proxy_settings)
        wireguard_settings = proxy_settings.get("wireguard") or {}
        for network in _normalized_peer_networks(wireguard_settings.get("peer_ips") or []):
            owners.setdefault(network, set()).add(uid)
    return owners


async def get_wireguard_tags(tags: Iterable[str]) -> list[str]:
    """Get WireGuard inbound tags from a list of tags (requires core manager; unused by global pool path)."""
    inbounds_by_tag = await core_manager.get_inbounds_by_tag()
    wireguard_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag in seen:
            continue
        if inbounds_by_tag.get(tag, {}).get("protocol") == "wireguard":
            seen.add(tag)
            wireguard_tags.append(tag)
    return wireguard_tags


async def get_wireguard_tags_from_groups(groups: Iterable) -> list[str]:
    """Get WireGuard inbound tags from a list of groups."""
    tags: list[str] = []
    for group in groups:
        if getattr(group, "is_disabled", False):
            continue
        if hasattr(group, "awaitable_attrs"):
            await group.awaitable_attrs.inbounds
        tags.extend(inbound.tag for inbound in group.inbounds)
    return await get_wireguard_tags(tags)


async def get_wireguard_inbound_tags_from_db(db: AsyncSession) -> set[str]:
    """Inbound tags (interface names) for all WireGuard cores."""
    rows = (await db.execute(select(CoreConfig).where(CoreConfig.type == CoreType.wg))).scalars().all()
    tags: set[str] = set()
    for row in rows:
        cfg = row.config or {}
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        name = (cfg or {}).get("interface_name")
        if name:
            tags.add(str(name).strip())
    return tags


async def user_in_wireguard_group(user: User, wg_tags: set[str]) -> bool:
    groups = user.__dict__.get("groups")
    if groups is None:
        groups = await user.awaitable_attrs.groups

    for group in groups:
        if group.is_disabled:
            continue
        inbounds = group.__dict__.get("inbounds")
        if inbounds is None:
            inbounds = await group.awaitable_attrs.inbounds
        for inbound in inbounds:
            if inbound.tag in wg_tags:
                return True
    return False


async def prepare_wireguard_proxy_settings(
    db: AsyncSession,
    proxy_settings: ProxyTable,
    groups: Iterable,
    *,
    exclude_user_id: int | None = None,
) -> ProxyTable:
    """Prepare WireGuard proxy settings with key generation and global pool IP allocation."""
    wireguard_tags = await get_wireguard_tags_from_groups(groups)
    if not wireguard_tags:
        return proxy_settings

    if proxy_settings.wireguard.public_key and not proxy_settings.wireguard.private_key:
        raise ValueError("wireguard private_key is required when user is assigned to a WireGuard interface")

    if not proxy_settings.wireguard.private_key:
        private_key, public_key = generate_wireguard_keypair()
        proxy_settings.wireguard.private_key = private_key
        proxy_settings.wireguard.public_key = public_key
    elif not proxy_settings.wireguard.public_key:
        proxy_settings.wireguard.public_key = get_wireguard_public_key(proxy_settings.wireguard.private_key)

    peer_ips = list(proxy_settings.wireguard.peer_ips or [])

    # Use merged allocate+validate function to avoid double DB scan
    peer_ips = await allocate_and_validate_peer_ips(db, peer_ips, exclude_user_id=exclude_user_id)

    proxy_settings.wireguard.peer_ips = peer_ips
    return proxy_settings


async def prepare_wireguard_keys_only(
    db: AsyncSession,
    proxy_settings: ProxyTable,
    groups: Iterable,
) -> ProxyTable:
    """Generate WireGuard keys without validation or IP allocation.

    Used when peer_ips haven't changed during user modification.
    Avoids expensive database scans for unchanged peer networks.
    """
    wireguard_tags = await get_wireguard_tags_from_groups(groups)
    if not wireguard_tags:
        return proxy_settings

    if proxy_settings.wireguard.public_key and not proxy_settings.wireguard.private_key:
        raise ValueError("wireguard private_key is required when user is assigned to a WireGuard interface")

    if not proxy_settings.wireguard.private_key:
        private_key, public_key = generate_wireguard_keypair()
        proxy_settings.wireguard.private_key = private_key
        proxy_settings.wireguard.public_key = public_key
    elif not proxy_settings.wireguard.public_key:
        proxy_settings.wireguard.public_key = get_wireguard_public_key(proxy_settings.wireguard.private_key)

    return proxy_settings


def prepare_wireguard_keys_for_member(proxy_settings: ProxyTable) -> ProxyTable:
    """Generate WireGuard keys for a user already known to belong to a WireGuard group."""
    if proxy_settings.wireguard.public_key and not proxy_settings.wireguard.private_key:
        raise ValueError("wireguard private_key is required when user is assigned to a WireGuard interface")

    if not proxy_settings.wireguard.private_key:
        private_key, public_key = generate_wireguard_keypair()
        proxy_settings.wireguard.private_key = private_key
        proxy_settings.wireguard.public_key = public_key
    elif not proxy_settings.wireguard.public_key:
        proxy_settings.wireguard.public_key = get_wireguard_public_key(proxy_settings.wireguard.private_key)

    return proxy_settings


async def bulk_reallocate_wireguard_peer_ips(
    db: AsyncSession,
    target_users: Iterable[User],
    *,
    dry_run: bool,
    replace_all: bool,
) -> dict:
    """
    Re-seat peer_ips for users in WireGuard groups when IPs are outside the current global pool
    or duplicated, or when replace_all is True. Preserves WireGuard keys. Syncs each updated user to nodes.

    ``target_users`` should be the users allowed by bulk scope (group/admin/user filters).
    """
    wg_tags = await get_wireguard_inbound_tags_from_db(db)
    if not wg_tags:
        return {
            "wireguard_inbound_tags": 0,
            "candidates": 0,
            "updated": 0,
            "dry_run": dry_run,
            "sample_usernames": [],
            "affected_users": 0,
        }

    users = list(target_users)
    eligible_users: list[tuple[User, list[str]]] = []
    to_touch: list[User] = []
    sample: list[str] = []

    for user in users:
        if not await user_in_wireguard_group(user, wg_tags):
            continue
        proxy_settings = ProxyTable.model_validate(user.proxy_settings or {})
        peer_ips = list(proxy_settings.wireguard.peer_ips or [])
        eligible_users.append((user, peer_ips))

    eligible_user_ids = {user.id for user, _ in eligible_users}
    all_peer_ip_rows = [{"id": user_id, **data} for user_id, data in (await get_all_wireguard_peer_ips_raw(db)).items()]
    peer_network_owners = _peer_network_owners_from_rows(all_peer_ip_rows)
    duplicated_user_ids: set[int] = set()
    for owner_ids in peer_network_owners.values():
        if len(owner_ids) > 1:
            target_owner_ids = owner_ids & eligible_user_ids
            if not target_owner_ids:
                continue
            if owner_ids <= eligible_user_ids:
                duplicated_user_ids.update(sorted(owner_ids)[1:])
            else:
                duplicated_user_ids.update(target_owner_ids)

    for user, peer_ips in eligible_users:
        need = False
        if replace_all:
            need = True
        elif not peer_ips:
            need = True
        elif peer_ips_outside_global_pool(peer_ips):
            need = True
        elif user.id in duplicated_user_ids:
            need = True

        if not need:
            continue
        to_touch.append(user)
        if len(sample) < 20:
            sample.append(user.username)

    if dry_run:
        n = len(to_touch)
        return {
            "wireguard_inbound_tags": len(wg_tags),
            "candidates": n,
            "updated": 0,
            "dry_run": True,
            "sample_usernames": sample,
            "affected_users": n,
        }

    if not to_touch:
        return {
            "wireguard_inbound_tags": len(wg_tags),
            "candidates": 0,
            "updated": 0,
            "dry_run": False,
            "sample_usernames": sample,
            "affected_users": 0,
        }

    excluded_user_ids = {user.id for user in to_touch}
    peer_ip_rows = [row for row in all_peer_ip_rows if row.get("id") not in excluded_user_ids]
    used_networks = collect_used_peer_networks_from_proxy_settings_rows(peer_ip_rows)

    updated = 0
    allocator = WireGuardPeerIPAllocator(used_networks)
    updated_users: list[User] = []
    for user in to_touch:
        proxy_settings = ProxyTable.model_validate(user.proxy_settings or {})
        try:
            prepared = prepare_wireguard_keys_for_member(proxy_settings)
        except ValueError:
            continue
        peer_ip = allocator.allocate()
        if peer_ip is None:
            continue
        prepared.wireguard.peer_ips = [peer_ip]
        user.proxy_settings = prepared.dict()
        updated_users.append(user)
        updated += 1

    if updated_users:
        await db.commit()
        await sync_users(updated_users)

    return {
        "wireguard_inbound_tags": len(wg_tags),
        "candidates": len(to_touch),
        "updated": updated,
        "dry_run": False,
        "sample_usernames": sample,
        "affected_users": updated,
    }
