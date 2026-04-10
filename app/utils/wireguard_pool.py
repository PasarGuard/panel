from __future__ import annotations

from ipaddress import IPv4Network, ip_address, ip_network

from config import WIREGUARD_GLOBAL_POOL as WIREGUARD_GLOBAL_POOL_RAW
from config import WIREGUARD_RESERVED_IPV4 as WIREGUARD_RESERVED_IPV4_RAW


def _parse_global_pool(raw: str) -> IPv4Network:
    try:
        n = ip_network(raw.strip(), strict=False)
    except ValueError as exc:
        raise ValueError(f"Invalid WIREGUARD_GLOBAL_POOL: {raw!r}") from exc
    if n.version != 4:
        raise ValueError("WIREGUARD_GLOBAL_POOL must be an IPv4 CIDR (e.g. 10.0.0.0/8)")
    return n


def _parse_reserved(raw: str) -> frozenset:
    out: set = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            addr = ip_address(part)
        except ValueError as exc:
            raise ValueError(f"Invalid address in WIREGUARD_RESERVED_IPV4: {part!r}") from exc
        if addr.version != 4:
            raise ValueError("WIREGUARD_RESERVED_IPV4 must list IPv4 addresses only")
        out.add(addr)
    return frozenset(out)


WIREGUARD_GLOBAL_POOL: IPv4Network = _parse_global_pool(WIREGUARD_GLOBAL_POOL_RAW)
WIREGUARD_RESERVED_IPV4: frozenset = _parse_reserved(WIREGUARD_RESERVED_IPV4_RAW)
