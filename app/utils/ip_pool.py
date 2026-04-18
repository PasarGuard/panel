from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.crud.user import get_all_wireguard_peer_ips_raw
from app.db.models import User

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
    """Get all currently used peer networks from the database.

    Uses dialect-specific optimized queries where available.
    Falls back to lightweight column-only query for all databases.
    """
    dialect = db.bind.dialect.name

    if dialect == "postgresql":
        return await _get_global_used_networks_postgresql(db, exclude_user_id=exclude_user_id)
    else:
        # MySQL and SQLite: use lightweight query fetching only id and proxy_settings
        return await _get_global_used_networks_lightweight(db, exclude_user_id=exclude_user_id)


async def _get_global_used_networks_postgresql(
    db: AsyncSession,
    *,
    exclude_user_id: int | None = None,
) -> set[IPv4Network | IPv6Network]:
    """PostgreSQL-optimized query using JSONB operators for native JSON extraction."""

    # Cast the JSON column to JSONB so SQLAlchemy exposes JSONB-specific operators.
    # Subscript access on a plain JSON column returns a BinaryExpression that lacks
    # JSONB methods (.astext, jsonb_array_elements_text, etc.).
    jsonb_col = cast(User.proxy_settings, JSONB)
    peer_ips_path = jsonb_col["wireguard"]["peer_ips"]

    # jsonb_array_elements_text unnests the array into individual text rows.
    # The IS NOT NULL guard skips users whose wireguard.peer_ips key is absent/null.
    stmt = select(func.jsonb_array_elements_text(peer_ips_path).label("peer_ip")).where(peer_ips_path.isnot(None))

    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)

    result = await db.execute(stmt)
    rows = result.all()

    used_ips: set[IPv4Network | IPv6Network] = set()
    for row in rows:
        peer_ip = row[0]
        if peer_ip:
            try:
                used_ips.add(ip_network(peer_ip, strict=False))
            except ValueError:
                continue

    return used_ips


async def _get_global_used_networks_lightweight(
    db: AsyncSession,
    *,
    exclude_user_id: int | None = None,
) -> set[IPv4Network | IPv6Network]:
    """Lightweight query fetching only id and proxy_settings columns."""
    user_data = await get_all_wireguard_peer_ips_raw(db, exclude_user_id=exclude_user_id)

    used_ips: set[IPv4Network | IPv6Network] = set()
    for user_id, data in user_data.items():
        proxy_settings = data.get("proxy_settings") or {}
        if isinstance(proxy_settings, str):
            import json

            proxy_settings = json.loads(proxy_settings)

        wireguard_settings = proxy_settings.get("wireguard") or {}
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
    """Pick first free IPv4 /32 in the global pool (sync; for migrations).

    Uses bitset-style integer lookup for O(1) per candidate instead of O(U) per candidate.
    """
    pool = WIREGUARD_GLOBAL_POOL
    start = int(pool.network_address)
    end = int(pool.broadcast_address)

    # Pre-build set of all blocked integer addresses (reserved + used) for O(1) lookup
    blocked: set[int] = set()

    # Add all reserved addresses
    for net in WIREGUARD_RESERVED:
        for addr in net:
            blocked.add(int(addr))

    # Add all used addresses (only IPv4)
    for net in used_networks:
        if net.version == 4:
            for addr in net:
                blocked.add(int(addr))

    # Scan for first free address, skipping network and broadcast
    for raw_candidate in range(start + 1, end):
        if raw_candidate not in blocked:
            return f"{ip_address(raw_candidate)}/32"

    return None


async def allocate_from_global_pool(
    db: AsyncSession,
    *,
    exclude_user_id: int | None = None,
) -> str | None:
    used_ips = await get_global_used_networks(db, exclude_user_id=exclude_user_id)
    return allocate_one_from_pool_sync(used_ips)


async def allocate_and_validate_peer_ips(
    db: AsyncSession,
    peer_ips: list[str],
    *,
    exclude_user_id: int | None = None,
) -> list[str]:
    """
    Allocate peer IPs from global pool if not provided, or validate provided peer IPs.

    Fetches the used networks from database once and reuses for both allocation and validation.
    This avoids double scanning the entire user table.

    Args:
        db: Database session
        peer_ips: List of peer IPs to use. If empty, allocates from global pool.
        exclude_user_id: User ID to exclude from used networks check (for updates)

    Returns:
        List of allocated or validated peer IPs

    Raises:
        ValueError: If peer IPs are invalid, in use, reserved, or if allocation fails
    """
    # Single DB fetch for both allocation and validation
    used_networks = await get_global_used_networks(db, exclude_user_id=exclude_user_id)

    if not peer_ips:
        # Allocation path: find first free IP from pool
        candidate = allocate_one_from_pool_sync(used_networks)
        if candidate is None:
            raise ValueError("unable to allocate wireguard peer IP")
        return [candidate]

    # Validation path: check provided IPs against used networks
    validate_peer_ips_within_global_pool(peer_ips)

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

    return peer_ips


async def validate_peer_ips_globally(
    db: AsyncSession,
    peer_ips: list[str],
    *,
    exclude_user_id: int | None = None,
) -> None:
    """
    Validate that supplied peer IPs/networks don't overlap with existing user's peer networks.

    Raises ValueError if any supplied IP/network overlaps with an existing user's peer networks.

    Note: For new code, consider using allocate_and_validate_peer_ips which is more efficient
    when allocation and validation need to happen together.
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
