from __future__ import annotations

from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app import on_startup
from app.core.manager import core_manager
from app.db import GetDB
from app.db.crud.user import get_users_with_proxy_settings
from app.models.proxy import ProxyTable
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key
from app.utils.ip_pool import allocate_from_global_pool, get_global_used_networks, validate_peer_ips_globally


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
    2. Allocates peer IPs from the global pool if not provided
    3. Validates globally unique peer IPs
    """
    wireguard_tags = await get_wireguard_tags_from_groups(groups)
    if not wireguard_tags:
        return proxy_settings

    # Key generation
    if proxy_settings.wireguard.public_key and not proxy_settings.wireguard.private_key:
        raise ValueError("wireguard private_key is required when user is assigned to a WireGuard interface")

    if not proxy_settings.wireguard.private_key:
        private_key, public_key = generate_wireguard_keypair()
        proxy_settings.wireguard.private_key = private_key
        proxy_settings.wireguard.public_key = public_key
    elif not proxy_settings.wireguard.public_key:
        proxy_settings.wireguard.public_key = get_wireguard_public_key(proxy_settings.wireguard.private_key)

    peer_ips = list(proxy_settings.wireguard.peer_ips or [])
    if not peer_ips:
        # Prefer allocating from the WireGuard interface networks (core config),
        # so that user addresses stay within the interface subnet (e.g. 10.8.0.0/24).
        inbounds_by_tag = await core_manager.get_inbounds_by_tag()
        used_networks = await get_global_used_networks(db, exclude_user_id=exclude_user_id)

        candidate = None
        for tag in wireguard_tags:
            inbound = inbounds_by_tag.get(tag) or {}
            addresses = inbound.get("address") or []
            if not isinstance(addresses, list):
                continue

            for cidr in addresses:
                if not isinstance(cidr, str) or not cidr.strip():
                    continue
                try:
                    from ipaddress import ip_interface, ip_network, ip_address

                    iface = ip_interface(cidr.strip())
                    network = ip_network(cidr.strip(), strict=False)
                    server_ip = iface.ip
                except Exception:
                    continue

                # Skip networks that are too small to allocate a peer.
                if network.num_addresses <= 2:
                    continue

                # Iterate usable hosts. For IPv4, this excludes network/broadcast automatically.
                # For IPv6, it excludes only network address; broadcast doesn't exist.
                for host_ip in network.hosts():
                    if host_ip == server_ip:
                        continue
                    # Avoid overlaps with existing assigned networks.
                    if any(host_ip in used for used in used_networks if used.version == host_ip.version):
                        continue
                    # Ensure canonical /32 or /128 peer assignment.
                    prefix = 32 if host_ip.version == 4 else 128
                    candidate = f"{ip_address(host_ip)}/{prefix}"
                    break

                if candidate:
                    break
            if candidate:
                break

        if candidate is None:
            # Fallback: allocate from global pool if interface networks are missing/invalid/full.
            candidate = await allocate_from_global_pool(db, exclude_user_id=exclude_user_id)

        if candidate is None:
            raise ValueError("unable to allocate wireguard peer IP")

        peer_ips = [candidate]

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
