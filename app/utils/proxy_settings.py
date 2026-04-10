from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from app.models.proxy import ProxyTable

WIREGUARD_AUTO_PEER_IPS_BY_SUBNET_KEY = "__auto_peer_ips_by_subnet"
_KEEP_EXISTING = object()


def normalize_proxy_settings_storage(proxy_settings: dict | None) -> dict:
    if not isinstance(proxy_settings, dict):
        return {}
    return deepcopy(proxy_settings)


def load_proxy_settings(proxy_settings: dict | None) -> ProxyTable:
    return ProxyTable.model_validate(proxy_settings or {})


def get_wireguard_auto_peer_ips_by_subnet(proxy_settings: dict | None) -> dict[str, str] | None:
    storage = normalize_proxy_settings_storage(proxy_settings)
    wireguard = storage.get("wireguard")
    if not isinstance(wireguard, dict) or WIREGUARD_AUTO_PEER_IPS_BY_SUBNET_KEY not in wireguard:
        return None

    raw_mapping = wireguard.get(WIREGUARD_AUTO_PEER_IPS_BY_SUBNET_KEY)
    if not isinstance(raw_mapping, dict):
        return {}

    mapping: dict[str, str] = {}
    for subnet, peer_ip in raw_mapping.items():
        if not isinstance(subnet, str) or not subnet.strip():
            continue
        if not isinstance(peer_ip, str) or not peer_ip.strip():
            continue
        mapping[subnet.strip()] = peer_ip.strip()
    return mapping


def has_wireguard_auto_peer_ips_marker(proxy_settings: dict | None) -> bool:
    return get_wireguard_auto_peer_ips_by_subnet(proxy_settings) is not None


def dump_proxy_settings_for_storage(
    proxy_settings: ProxyTable,
    existing_proxy_settings: dict | None = None,
    *,
    auto_peer_ips_by_subnet: Mapping[str, str] | None | object = _KEEP_EXISTING,
) -> dict:
    storage = proxy_settings.dict()

    if auto_peer_ips_by_subnet is _KEEP_EXISTING:
        preserved_mapping = get_wireguard_auto_peer_ips_by_subnet(existing_proxy_settings)
        if preserved_mapping is not None:
            storage.setdefault("wireguard", {})[WIREGUARD_AUTO_PEER_IPS_BY_SUBNET_KEY] = preserved_mapping
        return storage

    if auto_peer_ips_by_subnet is None:
        return storage

    storage.setdefault("wireguard", {})[WIREGUARD_AUTO_PEER_IPS_BY_SUBNET_KEY] = {
        str(subnet): str(peer_ip) for subnet, peer_ip in auto_peer_ips_by_subnet.items()
    }
    return storage


def update_wireguard_peer_ip_storage(
    existing_proxy_settings: dict | None,
    *,
    peer_ips: list[str],
    auto_peer_ips_by_subnet: Mapping[str, str] | None | object = _KEEP_EXISTING,
) -> dict:
    storage = normalize_proxy_settings_storage(existing_proxy_settings)
    wireguard = storage.setdefault("wireguard", {})
    if not isinstance(wireguard, dict):
        wireguard = {}
        storage["wireguard"] = wireguard

    wireguard["peer_ips"] = list(peer_ips)

    if auto_peer_ips_by_subnet is _KEEP_EXISTING:
        return storage

    if auto_peer_ips_by_subnet is None:
        wireguard.pop(WIREGUARD_AUTO_PEER_IPS_BY_SUBNET_KEY, None)
        return storage

    wireguard[WIREGUARD_AUTO_PEER_IPS_BY_SUBNET_KEY] = {
        str(subnet): str(peer_ip) for subnet, peer_ip in auto_peer_ips_by_subnet.items()
    }
    return storage
