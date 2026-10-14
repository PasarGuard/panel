"""Short in-process TTL cache for generated subscription payloads.

Client apps poll /sub far more often than hosts or user settings change.
A few seconds of reuse avoids rebuilding JSON/YAML on every pull. Each
Uvicorn worker has its own cache (same model as the sub-update buffer).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

SUB_CONFIG_CACHE_TTL_S = 15
SUB_CONFIG_CACHE_MAX = 4096

_cache: OrderedDict[tuple, tuple[float, str | bytes]] = OrderedDict()
_generation = 0
_inflight: dict[tuple, asyncio.Task[str | bytes]] = {}
_inflight_lock = asyncio.Lock()


class SubConfigKey(tuple):
    """A generated subscription key carrying the generation captured before rendering."""


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
    proxy_settings = getattr(user, "proxy_settings", None)
    if proxy_settings is not None and hasattr(proxy_settings, "model_dump"):
        proxy_settings = proxy_settings.model_dump(mode="json")
    elif proxy_settings is not None and hasattr(proxy_settings, "model_dump_json"):
        proxy_settings = proxy_settings.model_dump_json()
    proxy_key = hashlib.sha256(json.dumps(proxy_settings, sort_keys=True, default=str).encode()).hexdigest()
    # The rendered payload also includes admin/profile metadata and format variables.
    if hasattr(user, "model_dump"):
        user_state = user.model_dump(mode="json", exclude_computed_fields=True)
    else:
        user_state = vars(user) if hasattr(user, "__dict__") else str(user)
    user_key = hashlib.sha256(json.dumps(user_state, sort_keys=True, default=str).encode()).hexdigest()
    return SubConfigKey(
        (
            _generation,
            getattr(user, "id", None),
            config_format,
            bool(as_base64),
            bool(randomize_order),
            status_key,
            getattr(user, "data_limit", None),
            getattr(user, "used_traffic", None) if config_format == "wireguard" else None,
            expire_key,
            tuple(inbounds),
            proxy_key,
            user_key,
        )
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
    # An invalidation can arrive while the old generation is still rendering.
    if isinstance(key, SubConfigKey) and key[0] != _generation:
        return
    _cache[key] = (time.monotonic() + SUB_CONFIG_CACHE_TTL_S, value)
    _cache.move_to_end(key)
    while len(_cache) > SUB_CONFIG_CACHE_MAX:
        _cache.popitem(last=False)


async def get_or_create_sub_config(key: tuple, factory: Callable[[], Awaitable[str | bytes]]) -> str | bytes:
    """Return a cached config and coalesce concurrent renders for the same key."""
    cached = get_sub_config(key)
    if cached is not None:
        return cached

    async with _inflight_lock:
        task = _inflight.get(key)
        if task is None:
            task = asyncio.create_task(factory(), name="subscription-config-render")
            _inflight[key] = task

            def cleanup(completed):
                # A cancelled HTTP waiter does not cancel the shared render.
                # Its dictionary entry still has to be reclaimed at completion.
                if _inflight.get(key) is completed:
                    _inflight.pop(key, None)
                if not completed.cancelled() and completed.exception() is None:
                    put_sub_config(key, completed.result())

            task.add_done_callback(cleanup)

    try:
        value = await asyncio.shield(task)
        put_sub_config(key, value)
        return value
    finally:
        if task.done():
            async with _inflight_lock:
                if _inflight.get(key) is task:
                    _inflight.pop(key, None)


def clear_sub_config_cache() -> None:
    global _generation
    _generation += 1
    _cache.clear()
