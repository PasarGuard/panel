from __future__ import annotations

from collections.abc import Iterable
from ipaddress import ip_network

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.wireguard import (
    get_wg_cores,
    match_namespace,
    offset_valid,
    peer_host,
    sync_users_allocations,
    tags_from_groups,
    wg_core_tags,
    wg_namespaces,
)
from app.db.models import User
from app.models.proxy import ProxyTable
from app.node.sync import sync_users
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key
from config import wireguard_settings


async def wireguard_public_key_in_use(
    db: AsyncSession,
    public_key: str,
    *,
    exclude_user_id: int | None = None,
) -> bool:
    stmt = select(User.id).where(User.proxy_settings["wireguard"]["public_key"].as_string() == public_key).limit(1)
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    return (await db.execute(stmt)).first() is not None


async def ensure_unique_wireguard_public_key(
    db: AsyncSession,
    proxy_settings: ProxyTable,
    *,
    exclude_user_id: int | None = None,
) -> None:
    public_key = proxy_settings.wireguard.public_key
    if not public_key:
        return
    if await wireguard_public_key_in_use(db, public_key, exclude_user_id=exclude_user_id):
        raise ValueError("wireguard public_key is already assigned to another user")


async def user_has_wireguard_access(db: AsyncSession, groups: Iterable) -> bool:
    wg_tags = wg_core_tags(await get_wg_cores(db))
    return bool(wg_tags and wg_tags & await tags_from_groups(groups))


async def prepare_wireguard_keys(
    db: AsyncSession,
    proxy_settings: ProxyTable,
    groups: Iterable,
    *,
    exclude_user_id: int | None = None,
) -> ProxyTable:
    """Ensure WG keys for a user assigned to a WireGuard interface.

    Peer IPs are managed by the subnet pool (app/db/crud/wireguard.py), never here.
    """
    if not await user_has_wireguard_access(db, groups):
        return proxy_settings

    await ensure_unique_wireguard_public_key(db, proxy_settings, exclude_user_id=exclude_user_id)

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


def _empty_reallocate_result(dry_run: bool, *, wireguard_inbound_tags: int = 0) -> dict:
    return {
        "wireguard_inbound_tags": wireguard_inbound_tags,
        "candidates": 0,
        "updated": 0,
        "dry_run": dry_run,
        "sample_usernames": [],
        "affected_users": 0,
    }


def _peer_network(entry: str) -> str | None:
    try:
        return str(ip_network(str(entry).strip(), strict=False))
    except ValueError:
        return None


def _peer_ip_invalid(namespaces: dict, entry: str) -> bool:
    host = peer_host(entry)
    if host is None:
        return True
    ns = match_namespace(namespaces, *host)
    if ns is None:
        return True
    offset = host[1] - int(ns.subnet.network_address)
    return not offset_valid(ns, offset)


def _duplicate_owner_ids(owners: dict[str, set[int]], eligible_ids: set[int]) -> set[int]:
    """Users (within scope) that must give up their entry because it's shared with another user.

    If every owner of a duplicated value is in scope, all but the lowest id (kept) are flagged.
    Otherwise an out-of-scope owner keeps it and every in-scope owner is flagged instead.
    """
    flagged: set[int] = set()
    for owner_ids in owners.values():
        if len(owner_ids) <= 1:
            continue
        in_scope = owner_ids & eligible_ids
        if not in_scope:
            continue
        if owner_ids <= eligible_ids:
            flagged.update(sorted(owner_ids)[1:])
        else:
            flagged.update(in_scope)
    return flagged


async def bulk_reallocate_wireguard_peer_ips(
    db: AsyncSession,
    target_users: Iterable[User],
    *,
    dry_run: bool,
    replace_all: bool,
) -> dict:
    """
    Re-seat peer_ips for users in WireGuard groups when IPs are outside the current subnet
    pool or duplicated, or when replace_all is True. Preserves WireGuard keys unless the
    public key is duplicated. Actual (re)allocation goes through the subnet pool in
    app/db/crud/wireguard.py, so it can never collide with a concurrently-issued IP.

    ``target_users`` should be the users allowed by bulk scope (group/admin/user filters).
    """
    if not wireguard_settings.enabled:
        return _empty_reallocate_result(dry_run)

    cores = await get_wg_cores(db)
    wg_tags = wg_core_tags(cores)
    if not wg_tags:
        return _empty_reallocate_result(dry_run)

    users = list(target_users)
    tags_by_user: dict[int, set[str]] = {}
    eligible: list[User] = []
    for user in users:
        groups = user.__dict__.get("groups")
        if groups is None:
            groups = await user.awaitable_attrs.groups
        tags = await tags_from_groups(groups)
        if tags & wg_tags:
            tags_by_user[user.id] = tags
            eligible.append(user)

    if not eligible:
        return _empty_reallocate_result(dry_run, wireguard_inbound_tags=len(wg_tags))

    namespaces = wg_namespaces(cores)
    eligible_ids = {user.id for user in eligible}

    all_rows = (await db.execute(select(User.id, User.proxy_settings))).all()
    network_owners: dict[str, set[int]] = {}
    key_owners: dict[str, set[int]] = {}
    peer_ips_by_id: dict[int, list[str]] = {}
    for user_id, proxy_settings in all_rows:
        wg = dict((proxy_settings or {}).get("wireguard") or {})
        peer_ips = list(wg.get("peer_ips") or [])
        peer_ips_by_id[user_id] = peer_ips
        for entry in peer_ips:
            network = _peer_network(entry)
            if network is not None:
                network_owners.setdefault(network, set()).add(user_id)
        public_key = wg.get("public_key")
        if public_key:
            key_owners.setdefault(str(public_key), set()).add(user_id)

    duplicated_peer_ip_ids = _duplicate_owner_ids(network_owners, eligible_ids)
    duplicated_key_ids = _duplicate_owner_ids(key_owners, eligible_ids)

    needs_peer_ip: set[int] = set()
    needs_rekey: set[int] = set()
    to_touch: list[User] = []
    sample: list[str] = []
    for user in eligible:
        peer_ips = peer_ips_by_id.get(user.id, [])
        flag_ip = (
            replace_all
            or not peer_ips
            or user.id in duplicated_peer_ip_ids
            or any(_peer_ip_invalid(namespaces, entry) for entry in peer_ips)
        )
        flag_key = user.id in duplicated_key_ids
        if not flag_ip and not flag_key:
            continue
        if flag_ip:
            needs_peer_ip.add(user.id)
        if flag_key:
            needs_rekey.add(user.id)
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

    for user in to_touch:
        proxy_settings = dict(user.proxy_settings or {})
        wg = dict(proxy_settings.get("wireguard") or {})
        if user.id in needs_rekey:
            private_key, public_key = generate_wireguard_keypair()
            wg["private_key"] = private_key
            wg["public_key"] = public_key
        if user.id in needs_peer_ip:
            wg["peer_ips"] = []
        proxy_settings["wireguard"] = wg
        user.proxy_settings = proxy_settings

    await sync_users_allocations(db, to_touch, tags_by_user=tags_by_user)
    await db.commit()
    await sync_users(to_touch)

    return {
        "wireguard_inbound_tags": len(wg_tags),
        "candidates": len(to_touch),
        "updated": len(to_touch),
        "dry_run": False,
        "sample_usernames": sample,
        "affected_users": len(to_touch),
    }
