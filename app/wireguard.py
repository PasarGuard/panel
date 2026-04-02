from __future__ import annotations

from ipaddress import IPv4Network, IPv6Network, ip_address, ip_interface, ip_network
from typing import Iterable

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.manager import core_manager
from app.db.models import Group, ProxyInbound, User, inbounds_groups_association, users_groups_association
from app.models.proxy import ProxyTable
from app.utils.crypto import generate_wireguard_keypair, get_wireguard_public_key


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


async def get_wireguard_tags(tags: Iterable[str]) -> list[str]:
    inbounds_by_tag = await core_manager.get_inbounds_by_tag()
    return _unique_preserve_order(
        tag for tag in tags if inbounds_by_tag.get(tag, {}).get("protocol") == "wireguard"
    )


async def get_wireguard_tags_from_groups(groups: Iterable[Group]) -> list[str]:
    tags: list[str] = []
    for group in groups:
        if getattr(group, "is_disabled", False):
            continue
        if hasattr(group, "awaitable_attrs"):
            await group.awaitable_attrs.inbounds
        tags.extend(inbound.tag for inbound in group.inbounds)
    return await get_wireguard_tags(tags)


async def ensure_single_wireguard_interface_for_tags(tags: Iterable[str], *, context: str) -> str | None:
    wireguard_tags = await get_wireguard_tags(tags)
    if len(wireguard_tags) > 1:
        raise ValueError(f"{context} cannot be assigned to more than one WireGuard interface")
    return wireguard_tags[0] if wireguard_tags else None


async def ensure_single_wireguard_interface_for_groups(groups: Iterable[Group], *, context: str) -> str | None:
    wireguard_tags = await get_wireguard_tags_from_groups(groups)
    if len(wireguard_tags) > 1:
        raise ValueError(f"{context} cannot be assigned to more than one WireGuard interface")
    return wireguard_tags[0] if wireguard_tags else None


def _networks_overlap(left: IPv4Network | IPv6Network, right: IPv4Network | IPv6Network) -> bool:
    return left.version == right.version and left.overlaps(right)


async def _get_wireguard_inbound(interface_tag: str) -> dict:
    inbound = await core_manager.get_inbound_by_tag(interface_tag)
    if not inbound or inbound.get("protocol") != "wireguard":
        raise ValueError(f"WireGuard interface '{interface_tag}' not found")
    return inbound


def _get_interface_addresses(inbound: dict) -> list:
    addresses = inbound.get("address") or []
    if not addresses:
        raise ValueError(f"WireGuard interface '{inbound.get('tag', '')}' does not define any address ranges")
    return [ip_interface(address) for address in addresses]


async def _get_existing_wireguard_peer_networks(
    db: AsyncSession,
    interface_tag: str,
    *,
    exclude_user_id: int | None = None,
) -> list[IPv4Network | IPv6Network]:
    stmt = (
        select(User.id, User.proxy_settings)
        .select_from(User)
        .join(users_groups_association, User.id == users_groups_association.c.user_id)
        .join(Group, users_groups_association.c.groups_id == Group.id)
        .join(inbounds_groups_association, Group.id == inbounds_groups_association.c.group_id)
        .join(ProxyInbound, inbounds_groups_association.c.inbound_id == ProxyInbound.id)
        .where(and_(Group.is_disabled.is_(False), ProxyInbound.tag == interface_tag))
    )
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)

    rows = (await db.execute(stmt)).all()
    networks: list[IPv4Network | IPv6Network] = []
    seen_user_ids: set[int] = set()
    for user_id, proxy_settings in rows:
        if user_id in seen_user_ids:
            continue
        seen_user_ids.add(user_id)
        for peer_ip in proxy_settings.get("wireguard", {}).get("peer_ips", []) or []:
            networks.append(ip_network(peer_ip, strict=False))
    return networks


async def validate_wireguard_peer_ips(
    db: AsyncSession,
    interface_tag: str,
    peer_ips: list[str],
    *,
    exclude_user_id: int | None = None,
) -> None:
    existing_networks = await _get_existing_wireguard_peer_networks(
        db,
        interface_tag,
        exclude_user_id=exclude_user_id,
    )
    inbound = await _get_wireguard_inbound(interface_tag)
    interface_addresses = _get_interface_addresses(inbound)
    validated_networks: list[IPv4Network | IPv6Network] = []
    for peer_ip in peer_ips:
        candidate = ip_network(peer_ip, strict=False)
        if not any(candidate.version == interface.ip.version and candidate.subnet_of(interface.network) for interface in interface_addresses):
            raise ValueError(f"wireguard peer IP '{peer_ip}' is outside interface '{interface_tag}' address ranges")
        if any(candidate.version == interface.ip.version and interface.ip in candidate for interface in interface_addresses):
            raise ValueError(f"wireguard peer IP '{peer_ip}' overlaps the server address on interface '{interface_tag}'")
        if any(_networks_overlap(candidate, validated) for validated in validated_networks):
            raise ValueError(f"wireguard peer IP '{peer_ip}' overlaps another peer IP in the same user")
        if any(_networks_overlap(candidate, existing) for existing in existing_networks):
            raise ValueError(f"wireguard peer IP '{peer_ip}' is already in use on interface '{interface_tag}'")
        validated_networks.append(candidate)


def _allocate_from_interface(
    interface_cidr: str,
    used_networks: list[IPv4Network | IPv6Network],
) -> str | None:
    interface = ip_interface(interface_cidr)
    network = interface.network
    server_ip = interface.ip

    start = int(network.network_address)
    end = int(network.broadcast_address)
    for raw_candidate in range(start, end + 1):
        candidate = ip_address(raw_candidate)

        if candidate.version == 4 and network.prefixlen < 31:
            if candidate == network.network_address or candidate == network.broadcast_address:
                continue

        if candidate == server_ip:
            continue

        if any(candidate in existing_network for existing_network in used_networks if existing_network.version == candidate.version):
            continue

        suffix = 32 if candidate.version == 4 else 128
        return f"{candidate}/{suffix}"

    return None


async def allocate_wireguard_peer_ips(
    db: AsyncSession,
    interface_tag: str,
    *,
    exclude_user_id: int | None = None,
) -> list[str]:
    inbound = await _get_wireguard_inbound(interface_tag)
    addresses = inbound.get("address") or []

    used_networks = await _get_existing_wireguard_peer_networks(
        db,
        interface_tag,
        exclude_user_id=exclude_user_id,
    )

    allocated_peer_ips: list[str] = []
    for address in addresses:
        allocated = _allocate_from_interface(address, used_networks)
        if not allocated:
            raise ValueError(f"unable to allocate WireGuard peer IP for interface '{interface_tag}'")

        allocated_network = ip_network(allocated, strict=False)
        used_networks.append(allocated_network)
        allocated_peer_ips.append(str(allocated_network))

    return allocated_peer_ips


async def prepare_wireguard_proxy_settings(
    db: AsyncSession,
    proxy_settings: ProxyTable,
    groups: Iterable[Group],
    *,
    exclude_user_id: int | None = None,
) -> ProxyTable:
    interface_tag = await ensure_single_wireguard_interface_for_groups(groups, context="user")
    if not interface_tag:
        return proxy_settings

    if proxy_settings.wireguard.public_key and not proxy_settings.wireguard.private_key:
        raise ValueError("wireguard private_key is required when user is assigned to a WireGuard interface")

    if not proxy_settings.wireguard.private_key and not proxy_settings.wireguard.public_key:
        private_key, public_key = generate_wireguard_keypair()
        proxy_settings.wireguard.private_key = private_key
        proxy_settings.wireguard.public_key = public_key
    elif proxy_settings.wireguard.private_key and not proxy_settings.wireguard.public_key:
        proxy_settings.wireguard.public_key = get_wireguard_public_key(proxy_settings.wireguard.private_key)

    if proxy_settings.wireguard.peer_ips:
        await validate_wireguard_peer_ips(
            db,
            interface_tag,
            proxy_settings.wireguard.peer_ips,
            exclude_user_id=exclude_user_id,
        )
    else:
        proxy_settings.wireguard.peer_ips = await allocate_wireguard_peer_ips(
            db,
            interface_tag,
            exclude_user_id=exclude_user_id,
        )

    return proxy_settings
