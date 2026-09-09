"""Short in-process TTL cache for generated subscription payloads.

Client apps poll /sub far more often than hosts or user settings change.
A few seconds of reuse avoids rebuilding JSON/YAML on every pull. Each
Uvicorn worker has its own cache (same model as the sub-update buffer).
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

SUB_CONFIG_CACHE_TTL_S = 15
SUB_CONFIG_CACHE_MAX = 4096

_cache: OrderedDict[tuple, tuple[float, str | bytes]] = OrderedDict()


def make_sub_config_key(
    user: Any,
    config_format: str,
    as_base64: bool,
    randomize_order: bool,
) -> tuple:
    expire = getattr(user, "expire", None)
    expire_key = expire.timestamp() if hasattr(expire, "timestamp") else expire
    status = getattr(user, "status", None)
    status_key = status.value if hasattr(status, "value") else status
    inbounds = getattr(user, "inbounds", None) or ()
    return (
        getattr(user, "id", None),
        config_format,
        bool(as_base64),
        bool(randomize_order),
        status_key,
        getattr(user, "data_limit", None),
        expire_key,
        tuple(inbounds),
    )


def get_sub_config(key: tuple) -> str | bytes | None:
    item = _cache.get(key)
    if item is None:
        return None
    expires_at, value = item
    if expires_at <= time.monotonic():
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return value


def put_sub_config(key: tuple, value: str | bytes) -> None:
    _cache[key] = (time.monotonic() + SUB_CONFIG_CACHE_TTL_S, value)
    _cache.move_to_end(key)
    while len(_cache) > SUB_CONFIG_CACHE_MAX:
        _cache.popitem(last=False)


def clear_sub_config_cache() -> None:
    _cache.clear()
