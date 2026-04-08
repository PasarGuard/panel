from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_address, ip_interface, ip_network
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app import on_startup
from app.core.manager import core_manager
from app.db import GetDB
from app.db.crud.user import get_users_with_proxy_settings
from app.models.proxy import ProxyTable
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key
from app.utils.ip_pool import allocate_from_global_pool, get_global_used_networks, validate_peer_ips_globally
from app.utils.logger import get_logger

_logger = get_logger("wireguard-utils")


async def get_wireguard_tags(tags: Iterable[str]) -> list[str]:
    """Get WireGuard inbound tags from a list of tags."""
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


async def _wireguard_interface_networks_for_tags(wireguard_tags: list[str]) -> list[IPv4Network | IPv6Network]:
    """Collect `address` CIDR networks from core WireGuard inbounds for the given tags."""
    inbounds_by_tag = await core_manager.get_inbounds_by_tag()
    networks: list[IPv4Network | IPv6Network] = []
    for tag in wireguard_tags:
        inbound = inbounds_by_tag.get(tag) or {}
        addresses = inbound.get("address") or []
        if not isinstance(addresses, list):
            continue
        for cidr in addresses:
            if not isinstance(cidr, str) or not cidr.strip():
                continue
            try:
                networks.append(ip_network(cidr.strip(), strict=False))
            except ValueError:
                continue
    return networks


def _distinct_wireguard_networks_with_server(
    wireguard_tags: list[str],
    inbounds_by_tag: dict,
) -> list[tuple[IPv4Network | IPv6Network, object]]:
    """One row per distinct interface subnet (deduped), with server IP from core `address` line."""
    seen: set[str] = set()
    rows: list[tuple[IPv4Network | IPv6Network, object]] = []
    for tag in wireguard_tags:
        inbound = inbounds_by_tag.get(tag) or {}
        addresses = inbound.get("address") or []
        if not isinstance(addresses, list):
            continue
        for cidr in addresses:
            if not isinstance(cidr, str) or not cidr.strip():
                continue
            try:
                iface = ip_interface(cidr.strip())
                network = ip_network(cidr.strip(), strict=False)
            except ValueError:
                continue
            if network.num_addresses <= 2:
                continue
            key = str(network)
            if key in seen:
                continue
            seen.add(key)
            rows.append((network, iface.ip))
    return rows


def _peer_ip_covers_network(peer_ips: list[str], network: IPv4Network | IPv6Network) -> bool:
    for peer_ip in peer_ips:
        try:
            pn = ip_network(peer_ip, strict=False)
        except ValueError:
            continue
        if pn.version == network.version and pn.subnet_of(network):
            return True
    return False


def _allocate_peer_in_network(
    network: IPv4Network | IPv6Network,
    server_ip: object,
    used_networks: set[IPv4Network | IPv6Network],
) -> str | None:
    """Pick first free host in `network` excluding `server_ip` and `used_networks`."""
    for host_ip in network.hosts():
        if host_ip == server_ip:
            continue
        if any(host_ip in used for used in used_networks if used.version == host_ip.version):
            continue
        prefix = 32 if host_ip.version == 4 else 128
        return f"{ip_address(host_ip)}/{prefix}"
    return None


async def validate_manual_peer_ips_within_wireguard_subnets(
    peer_ips: list[str],
    wireguard_tags: list[str],
) -> None:
    """Reject manual peer IPs that are not contained in any core WireGuard interface network."""
    if not peer_ips:
        return
    networks = await _wireguard_interface_networks_for_tags(wireguard_tags)
    if not networks:
        return

    for peer_ip in peer_ips:
        try:
            pn = ip_network(peer_ip, strict=False)
        except ValueError as exc:
            raise ValueError(f"invalid IP/network format: '{peer_ip}'") from exc
        if not any(
            pn.version == iface.version and pn.subnet_of(iface)
            for iface in networks
        ):
            raise ValueError(
                f"peer IP '{peer_ip}' is not within any WireGuard interface address range for this user's groups"
            )


async def prepare_wireguard_proxy_settings(
    db: AsyncSession,
    proxy_settings: ProxyTable,
    groups: Iterable,
    *,
    exclude_user_id: int | None = None,
) -> ProxyTable:
    """Prepare WireGuard proxy settings with key generation and IP allocation.

    This function:
    1. Generates missing WireGuard keypairs
    2. Allocates one peer IP per distinct WireGuard interface subnet (core `address`),
       falling back to the global pool when a subnet is missing or full
    3. Fills any extra subnets when the user gains interfaces or had a legacy single IP
    4. Validates globally unique peer IPs
    """
    wireguard_tags = await get_wireguard_tags_from_groups(groups)
    if not wireguard_tags:
        return proxy_settings

    requested_peer_ips = list(proxy_settings.wireguard.peer_ips or [])

    # Key generation
    if proxy_settings.wireguard.public_key and not proxy_settings.wireguard.private_key:
        raise ValueError("wireguard private_key is required when user is assigned to a WireGuard interface")

    if not proxy_settings.wireguard.private_key:
        private_key, public_key = generate_wireguard_keypair()
        proxy_settings.wireguard.private_key = private_key
        proxy_settings.wireguard.public_key = public_key
    elif not proxy_settings.wireguard.public_key:
        proxy_settings.wireguard.public_key = get_wireguard_public_key(proxy_settings.wireguard.private_key)

    inbounds_by_tag = await core_manager.get_inbounds_by_tag()
    net_rows = _distinct_wireguard_networks_with_server(wireguard_tags, inbounds_by_tag)
    used_networks: set[IPv4Network | IPv6Network] = set(
        await get_global_used_networks(db, exclude_user_id=exclude_user_id)
    )

    peer_ips = list(requested_peer_ips)

    if requested_peer_ips:
        await validate_manual_peer_ips_within_wireguard_subnets(peer_ips, wireguard_tags)
        for p in peer_ips:
            try:
                used_networks.add(ip_network(p, strict=False))
            except ValueError:
                pass
    elif not peer_ips:
        # Allocate one /32 (or /128) per distinct WireGuard subnet the user can reach.
        if not net_rows:
            candidate = await allocate_from_global_pool(db, exclude_user_id=exclude_user_id)
            if candidate is None:
                raise ValueError("unable to allocate wireguard peer IP")
            peer_ips = [candidate]
            used_networks.add(ip_network(candidate, strict=False))
        else:
            for network, server_ip in net_rows:
                candidate = _allocate_peer_in_network(network, server_ip, used_networks)
                if candidate is None:
                    candidate = await allocate_from_global_pool(db, exclude_user_id=exclude_user_id)
                if candidate is None:
                    raise ValueError("unable to allocate wireguard peer IP for interface subnet")
                peer_ips.append(candidate)
                used_networks.add(ip_network(candidate, strict=False))

    # Fill missing subnets (e.g. user gained a second WG group, or legacy single global IP).
    for network, server_ip in net_rows:
        if _peer_ip_covers_network(peer_ips, network):
            continue
        candidate = _allocate_peer_in_network(network, server_ip, used_networks)
        if candidate is None:
            candidate = await allocate_from_global_pool(db, exclude_user_id=exclude_user_id)
        if candidate is None:
            raise ValueError("unable to allocate wireguard peer IP for additional interface subnet")
        peer_ips.append(candidate)
        used_networks.add(ip_network(candidate, strict=False))

    await validate_peer_ips_globally(db, peer_ips, exclude_user_id=exclude_user_id)

    proxy_settings.wireguard.peer_ips = peer_ips
    return proxy_settings


@on_startup
async def ensure_users_have_wireguard_keypairs():
    """Startup hook to ensure all users have WireGuard keypairs."""
    async with GetDB() as db:
        users = await get_users_with_proxy_settings(db)
        updated = False

        for db_user in users:
            proxy_settings = ProxyTable.model_validate(db_user.proxy_settings or {})
            wireguard_settings = proxy_settings.wireguard

            if not wireguard_settings.private_key:
                private_key, public_key = generate_wireguard_keypair()
                wireguard_settings.private_key = private_key
                wireguard_settings.public_key = public_key
                db_user.proxy_settings = proxy_settings.dict()
                updated = True
                continue

            if not wireguard_settings.public_key:
                wireguard_settings.public_key = get_wireguard_public_key(wireguard_settings.private_key)
                db_user.proxy_settings = proxy_settings.dict()
                updated = True

        if updated:
            await db.commit()


@on_startup
async def ensure_users_have_wireguard_peer_ips():
    """Persist auto-allocated peer IPs for WireGuard users and sync them to nodes (fixes empty DB vs subscription drift)."""
    from app.node.sync import sync_user

    async with GetDB() as db:
        users = await get_users_with_proxy_settings(db)
        updated_users: list = []

        for db_user in users:
            proxy_settings = ProxyTable.model_validate(db_user.proxy_settings or {})

            await db_user.awaitable_attrs.groups
            groups = [g for g in db_user.groups if not g.is_disabled]
            if not groups:
                continue

            wireguard_tags = await get_wireguard_tags_from_groups(groups)
            if not wireguard_tags:
                continue

            old_peer_ips = list(proxy_settings.wireguard.peer_ips or [])

            try:
                prepared = await prepare_wireguard_proxy_settings(
                    db, proxy_settings, groups, exclude_user_id=db_user.id
                )
            except ValueError as exc:
                _logger.warning(
                    'Skipping WireGuard peer IP backfill for user "%s" (id=%s): %s',
                    db_user.username,
                    db_user.id,
                    exc,
                )
                continue

            new_settings = prepared.dict()
            new_wireguard = new_settings.get("wireguard") or {}
            new_peer_ips = list(new_wireguard.get("peer_ips") or [])
            if not new_peer_ips:
                continue
            if sorted(new_peer_ips) == sorted(old_peer_ips):
                continue

            db_user.proxy_settings = new_settings
            updated_users.append(db_user)

        if not updated_users:
            return

        await db.commit()
        for db_user in updated_users:
            await sync_user(db_user)
