from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.user import get_users_with_proxy_settings
from .wireguard_pool import WIREGUARD_GLOBAL_POOL, WIREGUARD_RESERVED

# Backward-compatible names
GLOBAL_IP_POOL = WIREGUARD_GLOBAL_POOL
SERVER_RESERVED = WIREGUARD_RESERVED


def peer_ipv4_network_in_global_pool(net: IPv4Network | IPv6Network) -> bool:
    if net.version != 4:
        return False
    return net.subnet_of(WIREGUARD_GLOBAL_POOL)


def peer_ips_outside_global_pool(peer_ips: list[str]) -> bool:
    """True if any IPv4 peer CIDR is not contained in the configured global pool."""
    for peer_ip in peer_ips:
        try:
            candidate = ip_network(peer_ip, strict=False)
        except ValueError:
            continue
        if candidate.version == 4 and not peer_ipv4_network_in_global_pool(candidate):
            return True
    return False


def validate_peer_ips_within_global_pool(peer_ips: list[str]) -> None:
    """Require every IPv4 peer network to lie inside WIREGUARD_GLOBAL_POOL (IPv6 entries are not checked)."""
    for peer_ip in peer_ips:
        try:
            candidate = ip_network(peer_ip, strict=False)
        except ValueError:
            raise ValueError(f"invalid IP/network format: '{peer_ip}'")
        if candidate.version == 4 and not peer_ipv4_network_in_global_pool(candidate):
            raise ValueError(f"peer IP '{peer_ip}' is outside WIREGUARD_GLOBAL_POOL ({WIREGUARD_GLOBAL_POOL})")


async def get_global_used_networks(
    db: AsyncSession,
    *,
    exclude_user_id: int | None = None,
) -> set[IPv4Network | IPv6Network]:
    users = await get_users_with_proxy_settings(db, exclude_user_id=exclude_user_id)

    used_ips: set[IPv4Network | IPv6Network] = set()
    for user in users:
        wireguard_settings = {}
        if isinstance(user.proxy_settings, dict):
            wireguard_settings = user.proxy_settings.get("wireguard") or {}

        peer_ips = wireguard_settings.get("peer_ips") or []
        for peer_ip in peer_ips:
            try:
                used_ips.add(ip_network(peer_ip, strict=False))
            except ValueError:
                continue

    return used_ips


def collect_used_peer_networks_from_proxy_settings_rows(
    rows: list[dict],
    *,
    exclude_user_id: int | None = None,
) -> set[IPv4Network | IPv6Network]:
    """Sync helper for migrations: build used peer networks from user proxy_settings dicts."""
    used: set[IPv4Network | IPv6Network] = set()
    for row in rows:
        uid = row.get("id")
        if exclude_user_id is not None and uid == exclude_user_id:
            continue
        ps = row.get("proxy_settings") or {}
        if isinstance(ps, str):
            import json

            ps = json.loads(ps)
        wg = ps.get("wireguard") or {}
        for peer_ip in wg.get("peer_ips") or []:
            try:
                used.add(ip_network(peer_ip, strict=False))
            except ValueError:
                continue
    return used


def allocate_one_from_pool_sync(used_networks: set[IPv4Network | IPv6Network]) -> str | None:
    """Pick first free IPv4 /32 in the global pool (sync; for migrations)."""
    pool = WIREGUARD_GLOBAL_POOL
    start = int(pool.network_address)
    end = int(pool.broadcast_address)

    for raw_candidate in range(start, end + 1):
        candidate = ip_address(raw_candidate)

        if any(candidate in net for net in WIREGUARD_RESERVED):
            continue

        if candidate == pool.broadcast_address:
            continue

        if any(candidate in used_ip for used_ip in used_networks if used_ip.version == 4):
            continue

        return f"{candidate}/32"

    return None


async def allocate_from_global_pool(
    db: AsyncSession,
    *,
    exclude_user_id: int | None = None,
) -> str | None:
    used_ips = await get_global_used_networks(db, exclude_user_id=exclude_user_id)
    return allocate_one_from_pool_sync(used_ips)


async def validate_peer_ips_globally(
    db: AsyncSession,
    peer_ips: list[str],
    *,
    exclude_user_id: int | None = None,
) -> None:
    """
    Validate that supplied peer IPs/networks don't overlap with existing user's peer networks.

    Raises ValueError if any supplied IP/network overlaps with an existing user's peer networks.
    """
    used_networks = await get_global_used_networks(db, exclude_user_id=exclude_user_id)

    for peer_ip in peer_ips:
        try:
            candidate = ip_network(peer_ip, strict=False)
        except ValueError:
            raise ValueError(f"invalid IP/network format: '{peer_ip}'")

        if any(candidate.overlaps(used_ip) for used_ip in used_networks):
            raise ValueError(f"peer IP/network '{peer_ip}' is already in use by an existing user's peer network")

        candidate_ip = ip_address(candidate.network_address)
        if any(candidate_ip in net for net in WIREGUARD_RESERVED):
            raise ValueError(f"peer IP '{peer_ip}' is reserved")
