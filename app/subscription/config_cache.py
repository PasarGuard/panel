"""Short in-process TTL cache for generated subscription payloads.

Client apps poll /sub far more often than hosts or user settings change.
A few seconds of reuse avoids rebuilding JSON/YAML on every pull. Each
Uvicorn worker has its own cache (same model as the sub-update buffer).
"""

from __future__ import annotations

import asyncio
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


def _serialize_proxy_settings(proxy_settings: Any) -> str:
    if proxy_settings is None:
        return ""
    model_dump_json = getattr(proxy_settings, "model_dump_json", None)
    if callable(model_dump_json):
        return model_dump_json()
    if isinstance(proxy_settings, dict):
        return json.dumps(proxy_settings, sort_keys=True, separators=(",", ":"), default=str)
    as_dict = getattr(proxy_settings, "dict", None)
    if callable(as_dict):
        return json.dumps(as_dict(), sort_keys=True, separators=(",", ":"), default=str)
    if hasattr(proxy_settings, "__dict__"):
        return json.dumps(vars(proxy_settings), sort_keys=True, separators=(",", ":"), default=str)
    return str(proxy_settings)


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
    return (
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
        _serialize_proxy_settings(proxy_settings),
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


async def get_or_create_sub_config(key: tuple, factory: Callable[[], Awaitable[str | bytes]]) -> str | bytes:
    """Return a cached config and coalesce concurrent renders for the same key."""
    cached = get_sub_config(key)
    if cached is not None:
        return cached

    async with _inflight_lock:
        cached = get_sub_config(key)
        if cached is not None:
            return cached
        task = _inflight.get(key)
        if task is None:
            start_generation = _generation

            async def _runner() -> str | bytes:
                try:
                    value = await factory()
                    if _generation == start_generation:
                        put_sub_config(key, value)
                    return value
                finally:
                    if _inflight.get(key) is task:
                        _inflight.pop(key, None)

            task = asyncio.create_task(_runner(), name="subscription-config-render")

            def _cleanup(done_task: asyncio.Task[str | bytes]) -> None:
                if _inflight.get(key) is done_task:
                    _inflight.pop(key, None)
                if not done_task.cancelled():
                    done_task.exception()

            task.add_done_callback(_cleanup)
            _inflight[key] = task

    return await asyncio.shield(task)


def clear_sub_config_cache() -> None:
    global _generation
    _generation += 1
    _cache.clear()
