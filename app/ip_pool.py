from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


GLOBAL_IP_POOL = IPv4Network("10.0.0.0/8")
SERVER_IP = ip_address("10.0.0.1")


def is_server_ip(ip_str: str) -> bool:
    try:
        ip = ip_address(ip_str.split("/")[0])
        return ip == SERVER_IP
    except ValueError:
        return False


def is_in_global_pool(ip_str: str) -> bool:
    try:
        ip = ip_address(ip_str.split("/")[0])
        return ip.version == 4 and ip in GLOBAL_IP_POOL
    except ValueError:
        return False


async def get_global_used_ips(
    db: AsyncSession,
    *,
    exclude_user_id: int | None = None,
) -> set[IPv4Network | IPv6Network]:
    from app.db.models import User
    from app.models.proxy import get_all_wireguard_peer_ips
    from sqlalchemy import select

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

        peer_ips = get_all_wireguard_peer_ips(wireguard_settings)
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
    used_ips = await get_global_used_ips(db, exclude_user_id=exclude_user_id)

    start = int(GLOBAL_IP_POOL.network_address)
    end = int(GLOBAL_IP_POOL.broadcast_address)

    for raw_candidate in range(start, end + 1):
        candidate = ip_address(raw_candidate)

        if candidate == SERVER_IP:
            continue

        if candidate == GLOBAL_IP_POOL.network_address or candidate == GLOBAL_IP_POOL.broadcast_address:
            continue

        if any(candidate in used_ip for used_ip in used_ips if used_ip.version == 4):
            continue

        return f"{candidate}/32"

    return None


async def validate_global_ip_availability(
    db: AsyncSession,
    ip_str: str,
    *,
    exclude_user_id: int | None = None,
) -> bool:
    if not is_in_global_pool(ip_str):
        return True

    used_ips = await get_global_used_ips(db, exclude_user_id=exclude_user_id)
    try:
        ip = ip_network(ip_str, strict=False)
        return not any(ip.overlaps(used_ip) for used_ip in used_ips)
    except ValueError:
        return False
