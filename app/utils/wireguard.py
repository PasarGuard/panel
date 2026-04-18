from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.manager import core_manager
from app.db.models import CoreConfig, CoreType, User
from app.models.proxy import ProxyTable
from app.node.sync import sync_user
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key
from app.utils.ip_pool import (
    allocate_and_validate_peer_ips,
    peer_ips_outside_global_pool,
)


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
    await user.awaitable_attrs.groups
    for group in user.groups:
        if group.is_disabled:
            continue
        await group.awaitable_attrs.inbounds
        for inbound in group.inbounds:
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


async def bulk_reallocate_wireguard_peer_ips(
    db: AsyncSession,
    target_users: Iterable[User],
    *,
    dry_run: bool,
    replace_all: bool,
) -> dict:
    """
    Re-seat peer_ips for users in WireGuard groups when IPs are outside the current global pool
    or when replace_all is True. Preserves WireGuard keys. Syncs each updated user to nodes.

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
    to_touch: list[User] = []
    sample: list[str] = []

    for user in users:
        if not await user_in_wireguard_group(user, wg_tags):
            continue
        proxy_settings = ProxyTable.model_validate(user.proxy_settings or {})
        peer_ips = list(proxy_settings.wireguard.peer_ips or [])

        need = False
        if replace_all:
            need = True
        elif not peer_ips:
            need = True
        elif peer_ips_outside_global_pool(peer_ips):
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

    updated = 0
    for user in to_touch:
        proxy_settings = ProxyTable.model_validate(user.proxy_settings or {})
        await user.awaitable_attrs.groups
        groups = [g for g in user.groups if not g.is_disabled]
        proxy_settings.wireguard.peer_ips = []
        try:
            prepared = await prepare_wireguard_proxy_settings(db, proxy_settings, groups, exclude_user_id=user.id)
        except ValueError:
            continue
        user.proxy_settings = prepared.dict()
        await db.commit()
        await db.refresh(user)
        await sync_user(user)
        updated += 1

    return {
        "wireguard_inbound_tags": len(wg_tags),
        "candidates": len(to_touch),
        "updated": updated,
        "dry_run": False,
        "sample_usernames": sample,
        "affected_users": updated,
    }
