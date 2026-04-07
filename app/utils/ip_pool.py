from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


GLOBAL_IP_POOL = IPv4Network("10.0.0.0/8")
SERVER_RESERVED = {ip_address("10.0.0.0"), ip_address("10.0.0.1")}


async def get_global_used_networks(
    db: AsyncSession,
    *,
    exclude_user_id: int | None = None,
) -> set[IPv4Network | IPv6Network]:
    from sqlalchemy import select

    from app.db.models import User

    stmt = select(User)
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)
    result = await db.execute(stmt)
    users = result.scalars().all()

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


async def allocate_from_global_pool(
    db: AsyncSession,
    *,
    exclude_user_id: int | None = None,
) -> str | None:
    used_ips = await get_global_used_networks(db, exclude_user_id=exclude_user_id)

    start = int(GLOBAL_IP_POOL.network_address)
    end = int(GLOBAL_IP_POOL.broadcast_address)

    for raw_candidate in range(start, end + 1):
        candidate = ip_address(raw_candidate)

        if candidate in SERVER_RESERVED:
            continue

        if candidate == GLOBAL_IP_POOL.broadcast_address:
            continue

        if any(candidate in used_ip for used_ip in used_ips if used_ip.version == 4):
            continue

        return f"{candidate}/32"

    return None


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
            raise ValueError(f"peer IP/network '{peer_ip}' overlaps with an existing user's peer network")

        candidate_ip = ip_address(candidate.network_address)
        if candidate_ip in SERVER_RESERVED:
            raise ValueError(f"peer IP '{peer_ip}' is reserved for server use")
