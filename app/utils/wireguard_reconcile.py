from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_network
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.manager import core_manager
from app.db.crud.user import get_users_with_proxy_settings
from app.models.proxy import WireGuardPeerIPs
from app.utils.logger import get_logger
from app.utils.proxy_settings import (
    get_wireguard_auto_peer_ips_by_subnet,
    normalize_proxy_settings_storage,
    update_wireguard_peer_ip_storage,
)
from app.utils.wireguard import (
    _IPNetwork,
    _NetworkRow,
    _wireguard_tags_from_groups,
)

_logger = get_logger("wireguard-reconcile")


@dataclass
class _WireGuardReconcileState:
    user: object
    raw_proxy_settings: dict
    current_peer_ips: list[str]
    current_auto_map: dict[str, str] | None
    required_rows: list[_NetworkRow]


def _distinct_wireguard_networks_with_server(
    wireguard_tags: list[str],
    inbounds_by_tag: dict,
) -> list[_NetworkRow]:
    """One row per distinct interface subnet (deduped), with server IP from core `address` line."""
    from ipaddress import ip_interface

    seen: set[str] = set()
    rows: list[_NetworkRow] = []
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
    return _sort_network_rows(rows)


def _sort_network_rows(rows: list[_NetworkRow]) -> list[_NetworkRow]:
    return sorted(
        rows,
        key=lambda row: (
            row[0].version,
            int(row[0].network_address),
            row[0].prefixlen,
        ),
    )


def _allocate_peer_in_network(
    network: _IPNetwork,
    server_ip: object,
    used_networks: set[_IPNetwork],
) -> str | None:
    """Pick first free host in `network` excluding `server_ip` and `used_networks`."""
    from ipaddress import ip_address

    for host_ip in network.hosts():
        if host_ip == server_ip:
            continue
        if any(host_ip in used for used in used_networks if used.version == host_ip.version):
            continue
        prefix = 32 if host_ip.version == 4 else 128
        return f"{ip_address(host_ip)}/{prefix}"
    return None


def _normalize_peer_ips(peer_ips: list[str] | None) -> list[str]:
    return WireGuardPeerIPs.model_validate({"peer_ips": peer_ips}).peer_ips


def _peer_networks(peer_ips: list[str]) -> set[_IPNetwork]:
    networks: set[_IPNetwork] = set()
    for peer_ip in peer_ips:
        try:
            networks.add(ip_network(peer_ip, strict=False))
        except ValueError:
            continue
    return networks


def _peer_ip_fits_required_subnet(peer_ip: str, network: _IPNetwork) -> bool:
    try:
        peer_network = ip_network(peer_ip, strict=False)
    except ValueError:
        return False
    return peer_network.version == network.version and peer_network.subnet_of(network)


def _stored_auto_state_matches_required_subnets(
    proxy_settings: dict,
    current_auto_map: dict[str, str],
    required_rows: list[_NetworkRow],
) -> bool:
    required_subnets = [str(network) for network, _ in required_rows]
    if set(current_auto_map.keys()) != set(required_subnets):
        return False

    ordered_auto_peer_ips: list[str] = []
    for network, _ in required_rows:
        subnet_key = str(network)
        peer_ip = current_auto_map.get(subnet_key)
        if not peer_ip or not _peer_ip_fits_required_subnet(peer_ip, network):
            return False
        ordered_auto_peer_ips.append(peer_ip)

    normalized_auto_peer_ips = _normalize_peer_ips(ordered_auto_peer_ips)
    if len(normalized_auto_peer_ips) != len(ordered_auto_peer_ips):
        return False

    stored_peer_ips = _normalize_peer_ips(
        (proxy_settings.get("wireguard") or {}).get("peer_ips") or [],
    )
    return sorted(stored_peer_ips) == sorted(normalized_auto_peer_ips)


def wireguard_peer_ips_need_reconcile(
    proxy_settings: dict | None,
    required_rows: list[_NetworkRow],
    *,
    include_legacy_empty_peer_ips: bool = False,
) -> bool:
    raw_proxy_settings = normalize_proxy_settings_storage(proxy_settings)
    current_auto_map = get_wireguard_auto_peer_ips_by_subnet(raw_proxy_settings)
    current_peer_ips = _normalize_peer_ips(
        (raw_proxy_settings.get("wireguard") or {}).get("peer_ips") or [],
    )

    if current_auto_map is None:
        return include_legacy_empty_peer_ips and not current_peer_ips and bool(required_rows)

    return not _stored_auto_state_matches_required_subnets(
        raw_proxy_settings, current_auto_map, required_rows,
    )


async def reconcile_wireguard_peer_ips_for_users(
    db: AsyncSession,
    users: Iterable,
    *,
    include_legacy_empty_peer_ips: bool = False,
) -> list:
    deduped_users: dict[int, object] = {}
    for user in users:
        user_id = getattr(user, "id", None)
        if user_id is None:
            continue
        deduped_users[user_id] = user

    if not deduped_users:
        return []

    inbounds_by_tag = await core_manager.get_inbounds_by_tag()
    reconcile_states: list[_WireGuardReconcileState] = []

    for user in sorted(deduped_users.values(), key=lambda item: item.id):
        await user.awaitable_attrs.groups
        required_tags = await _wireguard_tags_from_groups(user.groups, inbounds_by_tag)
        required_rows = _distinct_wireguard_networks_with_server(required_tags, inbounds_by_tag)

        raw_proxy_settings = normalize_proxy_settings_storage(user.proxy_settings)
        if not wireguard_peer_ips_need_reconcile(
            raw_proxy_settings,
            required_rows,
            include_legacy_empty_peer_ips=include_legacy_empty_peer_ips,
        ):
            continue

        wg_section = raw_proxy_settings.get("wireguard") or {}
        reconcile_states.append(
            _WireGuardReconcileState(
                user=user,
                raw_proxy_settings=raw_proxy_settings,
                current_peer_ips=_normalize_peer_ips(wg_section.get("peer_ips") or []),
                current_auto_map=get_wireguard_auto_peer_ips_by_subnet(raw_proxy_settings),
                required_rows=required_rows,
            )
        )

    if not reconcile_states:
        return []

    mutable_user_ids = {state.user.id for state in reconcile_states}
    all_users = await get_users_with_proxy_settings(db)
    used_networks: set[_IPNetwork] = set()
    for user in all_users:
        if user.id in mutable_user_ids:
            continue
        wg_peer_ips = (user.proxy_settings.get("wireguard") or {}).get("peer_ips")
        used_networks.update(_peer_networks(_normalize_peer_ips(wg_peer_ips)))

    changed_users: list = []
    for state in reconcile_states:
        current_networks = _peer_networks(state.current_peer_ips)
        candidate_auto_map = state.current_auto_map or {}
        temp_used_networks = set(used_networks)
        proposed_auto_map: dict[str, str] = {}
        allocation_failed = False

        for network, _ in state.required_rows:
            subnet_key = str(network)
            current_peer_ip = candidate_auto_map.get(subnet_key)
            if not current_peer_ip or not _peer_ip_fits_required_subnet(current_peer_ip, network):
                continue
            peer_network = ip_network(current_peer_ip, strict=False)
            if any(peer_network.overlaps(used) for used in temp_used_networks):
                continue
            proposed_auto_map[subnet_key] = str(peer_network)
            temp_used_networks.add(peer_network)

        for network, server_ip in state.required_rows:
            subnet_key = str(network)
            if subnet_key in proposed_auto_map:
                continue
            candidate_peer_ip = _allocate_peer_in_network(network, server_ip, temp_used_networks)
            if candidate_peer_ip is None:
                allocation_failed = True
                break
            peer_network = ip_network(candidate_peer_ip, strict=False)
            proposed_auto_map[subnet_key] = candidate_peer_ip
            temp_used_networks.add(peer_network)

        if allocation_failed:
            used_networks.update(current_networks)
            _logger.warning(
                'Skipping WireGuard peer IP reconcile for user "%s" (id=%s): '
                "no free address in one or more interface subnets",
                state.user.username,
                state.user.id,
            )
            continue

        proposed_peer_ips = list(proposed_auto_map.values())
        desired_proxy_settings = update_wireguard_peer_ip_storage(
            state.raw_proxy_settings,
            peer_ips=proposed_peer_ips,
            auto_peer_ips_by_subnet=proposed_auto_map,
        )
        if desired_proxy_settings == state.raw_proxy_settings:
            used_networks = temp_used_networks
            continue

        state.user.proxy_settings = desired_proxy_settings
        changed_users.append(state.user)
        used_networks = temp_used_networks

    if changed_users:
        await db.commit()

    return changed_users
