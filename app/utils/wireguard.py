from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_network
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.manager import core_manager
from app.models.proxy import ProxyTable
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key
from app.utils.ip_pool import validate_peer_ips_globally

_IPNetwork = IPv4Network | IPv6Network
_NetworkRow = tuple[_IPNetwork, object]


async def _wireguard_tags_from_groups(groups: Iterable, inbounds_by_tag: dict) -> list[str]:
    """Filter WireGuard inbound tags from groups using a pre-fetched inbound lookup."""
    wireguard_tags: list[str] = []
    seen: set[str] = set()
    for group in groups:
        if getattr(group, "is_disabled", False):
            continue
        if hasattr(group, "awaitable_attrs"):
            await group.awaitable_attrs.inbounds
        for inbound in group.inbounds:
            if inbound.tag in seen:
                continue
            if inbounds_by_tag.get(inbound.tag, {}).get("protocol") != "wireguard":
                continue
            seen.add(inbound.tag)
            wireguard_tags.append(inbound.tag)
    return wireguard_tags


async def get_wireguard_tags_from_groups(groups: Iterable) -> list[str]:
    """Get WireGuard inbound tags from a list of groups."""
    inbounds_by_tag = await core_manager.get_inbounds_by_tag()
    return await _wireguard_tags_from_groups(groups, inbounds_by_tag)


async def _wireguard_interface_networks_for_tags(
    wireguard_tags: list[str],
    *,
    inbounds_by_tag: dict | None = None,
) -> list[_IPNetwork]:
    """Collect `address` CIDR networks from core WireGuard inbounds for the given tags."""
    if inbounds_by_tag is None:
        inbounds_by_tag = await core_manager.get_inbounds_by_tag()

    networks: list[_IPNetwork] = []
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


async def validate_manual_peer_ips_within_wireguard_subnets(
    peer_ips: list[str],
    wireguard_tags: list[str],
    *,
    inbounds_by_tag: dict | None = None,
) -> None:
    """Reject manual peer IPs that are not contained in any core WireGuard interface network."""
    if not peer_ips:
        return

    networks = await _wireguard_interface_networks_for_tags(wireguard_tags, inbounds_by_tag=inbounds_by_tag)
    if not networks:
        return

    for peer_ip in peer_ips:
        try:
            pn = ip_network(peer_ip, strict=False)
        except ValueError as exc:
            raise ValueError(f"invalid IP/network format: '{peer_ip}'") from exc
        if not any(pn.version == iface.version and pn.subnet_of(iface) for iface in networks):
            raise ValueError(
                f"peer IP '{peer_ip}' is not within any WireGuard interface address range for this user's groups"
            )


def _ensure_wireguard_keys(proxy_settings: ProxyTable) -> None:
    if proxy_settings.wireguard.public_key and not proxy_settings.wireguard.private_key:
        raise ValueError("wireguard private_key is required when user is assigned to a WireGuard interface")

    if not proxy_settings.wireguard.private_key:
        private_key, public_key = generate_wireguard_keypair()
        proxy_settings.wireguard.private_key = private_key
        proxy_settings.wireguard.public_key = public_key
    elif not proxy_settings.wireguard.public_key:
        proxy_settings.wireguard.public_key = get_wireguard_public_key(proxy_settings.wireguard.private_key)


async def prepare_wireguard_proxy_settings_input(
    db: AsyncSession,
    proxy_settings: ProxyTable,
    groups: Iterable,
    *,
    exclude_user_id: int | None = None,
) -> ProxyTable:
    """Prepare WireGuard user input without allocating peer IPs."""
    _ensure_wireguard_keys(proxy_settings)

    manual_peer_ips = list(proxy_settings.wireguard.peer_ips or [])
    if not manual_peer_ips:
        return proxy_settings

    wireguard_tags = await get_wireguard_tags_from_groups(groups)
    if wireguard_tags:
        await validate_manual_peer_ips_within_wireguard_subnets(manual_peer_ips, wireguard_tags)
    await validate_peer_ips_globally(db, manual_peer_ips, exclude_user_id=exclude_user_id)
    return proxy_settings
