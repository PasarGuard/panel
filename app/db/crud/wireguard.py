from __future__ import annotations

import json
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_interface, ip_network
from typing import Iterable

from sqlalchemy import and_, delete, insert, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CoreConfig,
    CoreType,
    Group,
    ProxyInbound,
    User,
    WireGuardSubnet,
    inbounds_groups_association,
    users_groups_association,
)
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key
from app.utils.logger import get_logger

logger = get_logger("wireguard-subnets")

FREE_IPS_LIMIT = 10000
# ponytail: free-list capped to bound JSON size; holes above the kept set stay
# reclaimable on reconcile (upgrade: sparse bitmap / run-length encoding).
FREE_OFFSETS_CAP = FREE_IPS_LIMIT


# --- pure helpers -----------------------------------------------------------


def core_config_dict(core: CoreConfig) -> dict:
    cfg = core.config or {}
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    return cfg


def wg_core_subnets(config: dict) -> list:
    """Unique client subnets of a WG core (IPv4 and/or IPv6), from interface addresses."""
    seen: dict[str, object] = {}
    for cidr in (config or {}).get("address") or []:
        try:
            net = ip_interface(str(cidr).strip()).network
        except ValueError:
            continue
        seen.setdefault(str(net), net)
    return list(seen.values())


def render_peer_ip(subnet, offset: int) -> str:
    host = type(subnet.network_address)(int(subnet.network_address) + offset)
    return f"{host}/{'32' if subnet.version == 4 else '128'}"


def peer_host(entry: str) -> tuple[int, int] | None:
    """(version, host_int) of a stored peer_ips entry; None if invalid."""
    try:
        net = ip_network(str(entry).strip(), strict=False)
    except ValueError:
        return None
    return net.version, int(net.network_address)


def _host_address(version: int, host_int: int):
    return IPv4Address(host_int) if version == 4 else IPv6Address(host_int)


@dataclass(frozen=True)
class WgNamespace:
    """One allocation namespace: an exact client subnet shared by every WG core that uses it."""

    key: str  # canonical str(subnet), e.g. "10.0.0.0/24" or "fd00::/64"
    subnet: object  # IPv4Network | IPv6Network
    tags: frozenset[str]
    reserved: frozenset[int]  # network, last, and server interface offsets


def wg_namespaces(cores: Iterable[CoreConfig]) -> dict[str, WgNamespace]:
    by_key: dict[str, list[tuple[dict, object]]] = {}
    for core in cores:
        cfg = core_config_dict(core)
        for subnet in wg_core_subnets(cfg):
            by_key.setdefault(str(subnet), []).append((cfg, subnet))

    namespaces: dict[str, WgNamespace] = {}
    for key, entries in by_key.items():
        subnet = entries[0][1]
        base = int(subnet.network_address)
        reserved = {0, subnet.num_addresses - 1}
        tags: set[str] = set()
        for cfg, _ in entries:
            tag = str(cfg.get("interface_name") or "").strip()
            if tag:
                tags.add(tag)
            for cidr in cfg.get("address") or []:
                try:
                    iface = ip_interface(str(cidr).strip())
                except ValueError:
                    continue
                if iface.version == subnet.version and iface.ip in subnet:
                    reserved.add(int(iface.ip) - base)
        namespaces[key] = WgNamespace(key=key, subnet=subnet, tags=frozenset(tags), reserved=frozenset(reserved))
    return _collapse_overlapping_namespaces(namespaces)


def _collapse_overlapping_namespaces(namespaces: dict[str, WgNamespace]) -> dict[str, WgNamespace]:
    """Keep the largest subnet when CIDRs overlap; merge tags/reserved from smaller ones into it."""
    if len(namespaces) < 2:
        return namespaces

    # largest first (smaller prefixlen), then stable by key
    ordered = sorted(namespaces.values(), key=lambda ns: (ns.subnet.prefixlen, ns.key))
    kept: dict[str, WgNamespace] = {}
    for ns in ordered:
        keeper = None
        for other in kept.values():
            if other.subnet.version != ns.subnet.version:
                continue
            if other.subnet.overlaps(ns.subnet):
                keeper = other
                break
        if keeper is None:
            kept[ns.key] = ns
            continue

        logger.warning(
            "WireGuard subnet %s overlaps %s; skipping smaller/overlapping pool, merging into %s",
            ns.key,
            keeper.key,
            keeper.key,
        )
        base = int(keeper.subnet.network_address)
        reserved = set(keeper.reserved)
        for offset in ns.reserved:
            host = _host_address(ns.subnet.version, int(ns.subnet.network_address) + offset)
            if host in keeper.subnet:
                reserved.add(int(host) - base)
        kept[keeper.key] = WgNamespace(
            key=keeper.key,
            subnet=keeper.subnet,
            tags=frozenset(keeper.tags | ns.tags),
            reserved=frozenset(reserved),
        )
    return kept


def wg_core_tags(cores: Iterable[CoreConfig]) -> set[str]:
    """Interface names (= inbound tags) of all WG cores, subnet or not."""
    tags: set[str] = set()
    for core in cores:
        tag = str(core_config_dict(core).get("interface_name") or "").strip()
        if tag:
            tags.add(tag)
    return tags


def offset_valid(ns: WgNamespace, offset: int) -> bool:
    return 0 < offset < ns.subnet.num_addresses - 1 and offset not in ns.reserved


def match_namespace(namespaces: dict[str, WgNamespace], version: int, host_int: int) -> WgNamespace | None:
    addr = _host_address(version, host_int)
    for ns in namespaces.values():
        if ns.subnet.version == version and addr in ns.subnet:
            return ns
    return None


def pick_peer_ip_for_inbound(inbound_addresses: Iterable[str], peer_ips: Iterable[str]) -> list[str]:
    """The user's peer IPs that belong to this inbound's subnet(s)."""
    subnets = wg_core_subnets({"address": list(inbound_addresses or [])})
    if not subnets:
        return []
    picked = []
    for entry in peer_ips or []:
        host = peer_host(entry)
        if host is None:
            continue
        addr = _host_address(*host)
        if any(addr in subnet for subnet in subnets):
            picked.append(str(entry))
    return picked


def _usable_capacity(ns: WgNamespace) -> int:
    last_host = ns.subnet.num_addresses - 1
    in_range_reserved = sum(1 for offset in ns.reserved if 0 < offset < last_host)
    return max(0, last_host - 1 - in_range_reserved)


def _take_offset(ns: WgNamespace, row: WireGuardSubnet) -> int:
    """Pop the lowest valid free offset, or advance the high-water mark. Mutates the row."""
    free = list(row.free_offsets or [])
    valid = [offset for offset in free if offset_valid(ns, offset)]
    if valid:
        offset = min(valid)
        free.remove(offset)
        row.free_offsets = free
        return offset
    offset = row.next_offset
    while offset in ns.reserved:
        offset += 1
    if offset >= ns.subnet.num_addresses - 1:
        raise ValueError(f"WireGuard subnet {ns.subnet} has no free addresses")
    row.next_offset = offset + 1
    return offset


def _trim_free(offsets: list[int]) -> list[int]:
    if len(offsets) <= FREE_OFFSETS_CAP:
        return offsets
    return sorted(offsets)[:FREE_OFFSETS_CAP]


def _give_back(row: WireGuardSubnet, offsets: Iterable[int]) -> None:
    current = set(row.free_offsets or [])
    add = [offset for offset in offsets if offset > 0 and offset < row.next_offset and offset not in current]
    if add:
        row.free_offsets = _trim_free(list(row.free_offsets or []) + add)


async def tags_from_groups(groups: Iterable) -> set[str]:
    """Inbound tags of enabled groups (for freshly-created users whose association rows aren't queryable yet)."""
    tags: set[str] = set()
    for group in groups or []:
        if getattr(group, "is_disabled", False):
            continue
        inbounds = group.__dict__.get("inbounds")
        if inbounds is None:
            inbounds = await group.awaitable_attrs.inbounds
        tags.update(inbound.tag for inbound in inbounds)
    return tags


def _ensure_wireguard_keys(db_user: User) -> bool:
    """Fill missing WG keys in proxy_settings. Returns True if the user was changed."""
    proxy_settings = dict(db_user.proxy_settings or {})
    wg = dict(proxy_settings.get("wireguard") or {})
    private_key = wg.get("private_key")
    if private_key and wg.get("public_key"):
        return False
    if private_key:
        wg["public_key"] = get_wireguard_public_key(private_key)
    else:
        wg["private_key"], wg["public_key"] = generate_wireguard_keypair()
    proxy_settings["wireguard"] = wg
    db_user.proxy_settings = proxy_settings
    return True


def _user_peer_ips(db_user_settings: dict | None) -> list[str]:
    return list(((db_user_settings or {}).get("wireguard") or {}).get("peer_ips") or [])


def _set_user_peer_ips(db_user: User, peer_ips: list[str]) -> None:
    proxy_settings = dict(db_user.proxy_settings or {})
    wg = dict(proxy_settings.get("wireguard") or {})
    wg["peer_ips"] = peer_ips
    proxy_settings["wireguard"] = wg
    db_user.proxy_settings = proxy_settings


def _peer_sort_key(entry: str) -> tuple[int, int]:
    host = peer_host(entry)
    return host if host is not None else (99, 0)


# --- queries ----------------------------------------------------------------


async def get_wg_cores(db: AsyncSession) -> list[CoreConfig]:
    result = await db.execute(select(CoreConfig).where(CoreConfig.type == CoreType.wg))
    return list(result.scalars().all())


async def get_users_accessible_tags(db: AsyncSession, user_ids: list[int]) -> dict[int, set[str]]:
    """user_id -> inbound tags reachable through enabled groups. One joined SELECT."""
    if not user_ids:
        return {}
    stmt = (
        select(users_groups_association.c.user_id, ProxyInbound.tag)
        .join(
            Group,
            and_(Group.id == users_groups_association.c.groups_id, Group.is_disabled.is_(False)),
        )
        .join(inbounds_groups_association, inbounds_groups_association.c.group_id == Group.id)
        .join(ProxyInbound, ProxyInbound.id == inbounds_groups_association.c.inbound_id)
        .where(users_groups_association.c.user_id.in_(user_ids))
    )
    tags_by_user: dict[int, set[str]] = {}
    for user_id, tag in (await db.execute(stmt)).all():
        tags_by_user.setdefault(user_id, set()).add(tag)
    return tags_by_user


async def _lock_subnet_rows(db: AsyncSession, keys: Iterable[str]) -> dict[str, WireGuardSubnet]:
    """Get-or-create the pool rows and lock them for this transaction (sorted for deadlock safety)."""
    keys = sorted(set(keys))
    if not keys:
        return {}
    dialect = db.bind.dialect.name
    values = [{"network": key, "next_offset": 1, "free_offsets": []} for key in keys]
    if dialect == "postgresql":
        stmt = pg_insert(WireGuardSubnet).on_conflict_do_nothing(index_elements=["network"])
    elif dialect == "mysql":
        stmt = mysql_insert(WireGuardSubnet).on_duplicate_key_update(network=WireGuardSubnet.network)
    else:  # SQLite
        stmt = insert(WireGuardSubnet).prefix_with("OR IGNORE")
    await db.execute(stmt, values)

    stmt = (
        select(WireGuardSubnet)
        .where(WireGuardSubnet.network.in_(keys))
        .order_by(WireGuardSubnet.network)
        .execution_options(populate_existing=True)
    )
    if dialect != "sqlite":  # SQLite serializes writes; FOR UPDATE is a no-op there anyway
        stmt = stmt.with_for_update()
    rows = (await db.execute(stmt)).scalars().all()
    return {row.network: row for row in rows}


# --- sync (the single trigger) ----------------------------------------------


async def sync_users_allocations(
    db: AsyncSession,
    users: list[User],
    *,
    tags_by_user: dict[int, set[str]] | None = None,
) -> list[User]:
    """Reconcile each user's wireguard peer_ips and keys with their current group access.

    Allocates from the subnet pool rows for newly-accessible subnets, releases entries for
    subnets the user can no longer reach, and fills missing WG keys. All pool updates and
    user updates happen in the caller's transaction. Flushes; the caller commits.
    Returns the users that changed.
    """
    if not users:
        return []
    namespaces = wg_namespaces(await get_wg_cores(db))
    if tags_by_user is None:
        tags_by_user = await get_users_accessible_tags(db, [user.id for user in users])

    touched_keys: set[str] = set()
    for user in users:
        tags = tags_by_user.get(user.id, set())
        touched_keys.update(ns.key for ns in namespaces.values() if ns.tags & tags)
        for entry in _user_peer_ips(user.proxy_settings):
            host = peer_host(entry)
            if host is not None and (ns := match_namespace(namespaces, *host)):
                touched_keys.add(ns.key)
    rows = await _lock_subnet_rows(db, touched_keys)

    changed: list[User] = []
    for user in users:
        tags = tags_by_user.get(user.id, set())
        targets = {ns.key for ns in namespaces.values() if ns.tags & tags}
        old_ips = _user_peer_ips(user.proxy_settings)

        kept: dict[str, int] = {}
        for entry in old_ips:
            host = peer_host(entry)
            ns = match_namespace(namespaces, *host) if host is not None else None
            if ns is None:
                continue  # foreign/legacy entry: drop, nothing to give back
            offset = host[1] - int(ns.subnet.network_address)
            if ns.key in targets and ns.key not in kept and offset_valid(ns, offset):
                kept[ns.key] = offset
            else:
                _give_back(rows[ns.key], [offset])

        for key in sorted(targets - set(kept)):
            kept[key] = _take_offset(namespaces[key], rows[key])

        new_ips = sorted(
            (render_peer_ip(namespaces[key].subnet, offset) for key, offset in kept.items()),
            key=_peer_sort_key,
        )
        user_changed = False
        if new_ips != old_ips:
            _set_user_peer_ips(user, new_ips)
            user_changed = True
        if targets and _ensure_wireguard_keys(user):
            user_changed = True
        if user_changed:
            changed.append(user)

    if changed or rows:
        await db.flush()
    return changed


async def sync_user_allocations(
    db: AsyncSession,
    db_user: User,
    *,
    accessible_tags: set[str] | None = None,
) -> bool:
    tags_by_user = {db_user.id: accessible_tags} if accessible_tags is not None else None
    return bool(await sync_users_allocations(db, [db_user], tags_by_user=tags_by_user))


async def _release_proxy_settings(db: AsyncSession, settings_list: Iterable[dict | None]) -> None:
    namespaces = wg_namespaces(await get_wg_cores(db))
    releases: dict[str, list[int]] = {}
    for proxy_settings in settings_list:
        for entry in _user_peer_ips(proxy_settings):
            host = peer_host(entry)
            if host is not None and (ns := match_namespace(namespaces, *host)):
                releases.setdefault(ns.key, []).append(host[1] - int(ns.subnet.network_address))
    if not releases:
        return
    rows = await _lock_subnet_rows(db, releases)
    for key, offsets in releases.items():
        _give_back(rows[key], offsets)
    await db.flush()


async def release_users_allocations(db: AsyncSession, users: list[User]) -> None:
    """Give the users' peer IPs back to the pool (called right before user deletion)."""
    if not users:
        return
    await _release_proxy_settings(db, [user.proxy_settings for user in users])


async def release_allocations_by_user_ids(db: AsyncSession, user_ids: list[int]) -> None:
    """Same as release_users_allocations for delete paths that only hold user ids."""
    if not user_ids:
        return
    settings_list = (await db.execute(select(User.proxy_settings).where(User.id.in_(user_ids)))).scalars().all()
    await _release_proxy_settings(db, settings_list)


# --- full rebuild (core lifecycle & repair) ---------------------------------


async def reconcile_wireguard_subnets(db: AsyncSession) -> list[int]:
    """Rebuild pool rows and fix user peer_ips from ground truth after a WG core change.

    Handles subnet resize/move, server-IP moves, interface renames, duplicate IPs and
    orphaned namespaces. Flushes; the caller commits. Returns changed user ids.
    """
    namespaces = wg_namespaces(await get_wg_cores(db))

    # Lock live namespaces up front so sync cannot race the in-memory alloc pass.
    # Also lock any orphan pool rows we are about to drop.
    if namespaces:
        orphan_stmt = select(WireGuardSubnet.network).where(WireGuardSubnet.network.not_in(list(namespaces)))
    else:
        orphan_stmt = select(WireGuardSubnet.network)
    orphan_keys = (await db.execute(orphan_stmt)).scalars().all()
    await _lock_subnet_rows(db, list(namespaces) + list(orphan_keys))

    # ponytail: full lightweight user scan — core saves are rare admin operations
    user_rows = (await db.execute(select(User.id, User.proxy_settings))).all()
    all_tags = {tag for ns in namespaces.values() for tag in ns.tags}
    eligible_tags = await get_users_accessible_tags(db, [row[0] for row in user_rows]) if all_tags else {}

    used: dict[str, set[int]] = {key: set() for key in namespaces}
    desired: dict[int, list[str]] = {}
    need_alloc: dict[str, list[int]] = {}  # key -> user_ids (in scan order)
    for user_id, proxy_settings in user_rows:
        tags = eligible_tags.get(user_id, set())
        targets = {ns.key for ns in namespaces.values() if ns.tags & tags}
        old_ips = _user_peer_ips(proxy_settings)
        kept: dict[str, int] = {}
        for entry in old_ips:
            host = peer_host(entry)
            ns = match_namespace(namespaces, *host) if host is not None else None
            if ns is None:
                continue
            offset = host[1] - int(ns.subnet.network_address)
            # first holder keeps a duplicated IP; later holders get reallocated
            if ns.key in targets and ns.key not in kept and offset_valid(ns, offset) and offset not in used[ns.key]:
                kept[ns.key] = offset
                used[ns.key].add(offset)
        for key in sorted(targets - set(kept)):
            need_alloc.setdefault(key, []).append(user_id)
        desired[user_id] = [render_peer_ip(namespaces[key].subnet, offset) for key, offset in sorted(kept.items())]

    # in-memory allocation under the row locks taken above
    granted: dict[int, dict[str, int]] = {}  # user_id -> {key: offset}
    for key, user_ids in need_alloc.items():
        ns = namespaces[key]
        cursor = 1
        for user_id in user_ids:
            while cursor in ns.reserved or cursor in used[key]:
                cursor += 1
            if cursor >= ns.subnet.num_addresses - 1:
                logger.warning(f"WireGuard subnet {ns.subnet} exhausted; user {user_id} left without an IP")
                continue
            used[key].add(cursor)
            granted.setdefault(user_id, {})[key] = cursor
            cursor += 1

    changed_ids: list[int] = []
    settings_by_id = {row[0]: row[1] for row in user_rows}
    for user_id, ips in desired.items():
        for key, offset in sorted(granted.get(user_id, {}).items()):
            ips.append(render_peer_ip(namespaces[key].subnet, offset))
        ips.sort(key=_peer_sort_key)
        if ips != _user_peer_ips(settings_by_id[user_id]):
            changed_ids.append(user_id)

    if changed_ids:
        users = (await db.execute(select(User).where(User.id.in_(changed_ids)))).scalars().all()
        for user in users:
            _set_user_peer_ips(user, desired[user.id])
            if desired[user.id]:
                _ensure_wireguard_keys(user)

    # rebuild pool rows from the used sets; drop rows for dead namespaces
    if used:
        await db.execute(delete(WireGuardSubnet).where(WireGuardSubnet.network.not_in(list(used))))
        rows = await _lock_subnet_rows(db, used)
        for key, offsets in used.items():
            ns = namespaces[key]
            row = rows[key]
            row.next_offset = max(offsets) + 1 if offsets else 1
            row.free_offsets = _trim_free(
                [offset for offset in range(1, row.next_offset) if offset not in offsets and offset_valid(ns, offset)]
            )
    else:
        await db.execute(delete(WireGuardSubnet))
    await db.flush()
    return changed_ids


# --- visibility -------------------------------------------------------------


async def get_subnet_usage(db: AsyncSession, *, free_limit: int = FREE_IPS_LIMIT) -> list[dict]:
    """Per-subnet address usage: capacity, used/free counts, and the first free IPs."""
    namespaces = wg_namespaces(await get_wg_cores(db))
    pool_rows = (await db.execute(select(WireGuardSubnet))).scalars().all()
    rows_by_key = {row.network: row for row in pool_rows}

    usage: list[dict] = []
    for key in sorted(namespaces):
        ns = namespaces[key]
        row = rows_by_key.get(key)
        next_offset = row.next_offset if row else 1
        free_list = sorted(offset for offset in (row.free_offsets if row else []) or [] if offset_valid(ns, offset))
        reserved_below = sum(1 for offset in ns.reserved if 0 < offset < next_offset)
        used = max(0, (next_offset - 1) - reserved_below - len(free_list))
        capacity = _usable_capacity(ns)

        free_ips = [
            str(_host_address(ns.subnet.version, int(ns.subnet.network_address) + offset))
            for offset in free_list[:free_limit]
        ]
        offset = next_offset
        last_host = ns.subnet.num_addresses - 1
        while len(free_ips) < free_limit and offset < last_host:
            if offset not in ns.reserved:
                free_ips.append(str(_host_address(ns.subnet.version, int(ns.subnet.network_address) + offset)))
            offset += 1

        usage.append(
            {
                "subnet": key,
                "interface_tags": sorted(ns.tags),
                "capacity": capacity,
                "used": used,
                "free": max(0, capacity - used),
                "free_ips": free_ips,
            }
        )
    return usage
