from __future__ import annotations

from ipaddress import IPv4Network, ip_network

from config import WIREGUARD_GLOBAL_POOL as WIREGUARD_GLOBAL_POOL_RAW
from config import WIREGUARD_RESERVED as WIREGUARD_RESERVED_RAW


def _parse_global_pool(raw: str) -> IPv4Network:
    try:
        n = ip_network(raw.strip(), strict=False)
    except ValueError as exc:
        raise ValueError(f"Invalid WIREGUARD_GLOBAL_POOL: {raw!r}") from exc
    if n.version != 4:
        raise ValueError("WIREGUARD_GLOBAL_POOL must be an IPv4 CIDR (e.g. 10.0.0.0/8)")
    return n


def _parse_reserved_networks(raw: str) -> frozenset[IPv4Network]:
    """Comma-separated IPv4 CIDR subnets whose addresses are never auto-assigned from the pool."""
    out: set[IPv4Network] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            net = ip_network(part, strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid CIDR in WIREGUARD_RESERVED: {part!r}") from exc
        if net.version != 4:
            raise ValueError(f"WIREGUARD_RESERVED must be IPv4 CIDR subnets (e.g. 10.0.0.0/31): {part!r}")
        out.add(net)
    return frozenset(out)


WIREGUARD_GLOBAL_POOL: IPv4Network = _parse_global_pool(WIREGUARD_GLOBAL_POOL_RAW)
WIREGUARD_RESERVED: frozenset[IPv4Network] = _parse_reserved_networks(WIREGUARD_RESERVED_RAW)
