"""Drop duplicate notifications when every uvicorn worker observes the same event."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import inspect
import time
from collections import OrderedDict
from typing import Any

from app.nats import is_nats_enabled
from app.nats.kv_cas import kv_cas_json, kv_get_json
from app.utils.logger import get_logger
from config import server_settings

logger = get_logger("Notification")

DEDUP_WINDOW_SECONDS = 15.0
MAX_LOCAL_CLAIMS = 4096
MAX_SHARED_CLAIMS = 4096
SHARED_PRUNE_BATCH = 16
_local_claims: dict[str, float] = {}
_local_lock = asyncio.Lock()
_shared_claims: OrderedDict[str, float] = OrderedDict()
_shared_claims_kv: Any = None
_shared_claims_lock = asyncio.Lock()
_nc = None
_kv = None
_kv_lock = asyncio.Lock()


def notification_fingerprint(event_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    parts = [event_name]
    for value in (*args, *kwargs.values()):
        if value is None or isinstance(value, bool):
            continue
        ident = _identity(value)
        if ident:
            parts.append(ident)
            break
    raw = "|".join(parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:24]
    return f"nd.{digest}"


def _identity(value: Any) -> str:
    if hasattr(value, "id") and getattr(value, "id", None) is not None:
        return f"id:{value.id}"
    if hasattr(value, "username") and getattr(value, "username", None):
        return f"user:{value.username}"
    if hasattr(value, "name") and getattr(value, "name", None):
        return f"name:{value.name}"
    if isinstance(value, (str, int)):
        return str(value)[:80]
    return ""


async def claim_notification_slot(event_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool:
    """Return True if this worker should emit the notification."""
    if server_settings.workers <= 1:
        return True

    key = notification_fingerprint(event_name, args, kwargs)
    now = time.time()
    async with _local_lock:
        _prune_local(now)
        expires_at = _local_claims.get(key, 0)
        if expires_at > now:
            logger.debug("Skipping duplicate notification %s (%s)", event_name, key)
            return False
        _local_claims[key] = now + DEDUP_WINDOW_SECONDS

    if not is_nats_enabled():
        return True

    try:
        if not await _claim_shared(key, now):
            logger.debug("Skipping duplicate notification %s claimed by another worker (%s)", event_name, key)
            return False
    except Exception as exc:
        logger.debug("Notification dedup store unavailable for %s: %s", event_name, exc)
    return True


def _prune_local(now: float) -> None:
    expired = [key for key, expires_at in _local_claims.items() if expires_at <= now]
    for key in expired:
        del _local_claims[key]
    while len(_local_claims) >= MAX_LOCAL_CLAIMS:
        _local_claims.pop(next(iter(_local_claims)))


def _is_nc_usable(nc: Any) -> bool:
    is_closed = getattr(nc, "is_closed", False)
    if isinstance(is_closed, bool) and is_closed:
        return False
    is_connected = getattr(nc, "is_connected", True)
    return not (isinstance(is_connected, bool) and not is_connected)


async def _close_nc_quietly(nc: Any) -> None:
    is_closed = getattr(nc, "is_closed", False)
    if isinstance(is_closed, bool) and is_closed:
        return
    close = getattr(nc, "close", None)
    if callable(close):
        with contextlib.suppress(Exception):
            result = close()
            if inspect.isawaitable(result):
                await result


async def close_notification_dedup() -> None:
    """Close the NATS connection used by notification deduplication and reset state."""
    global _nc, _kv, _shared_claims_kv
    async with _kv_lock:
        nc = _nc
        _nc = None
        _kv = None
        async with _shared_claims_lock:
            _shared_claims.clear()
            _shared_claims_kv = None
        if nc is not None:
            await _close_nc_quietly(nc)


async def _get_kv():
    global _nc, _kv
    if _kv is not None and (_nc is None or _is_nc_usable(_nc)):
        return _kv
    async with _kv_lock:
        if _kv is not None and (_nc is None or _is_nc_usable(_nc)):
            return _kv
        if _nc is not None:
            await _close_nc_quietly(_nc)
            _nc = None
        _kv = None
        from app.nats.client import setup_nats_kv
        from config import nats_settings

        nc, _, kv = await setup_nats_kv(nats_settings.scheduler_leader_kv_bucket)
        if kv is None:
            if nc is not None:
                await _close_nc_quietly(nc)
            return None
        _nc = nc
        _kv = kv
        return _kv


def _record_shared_claim_unlocked(key: str, expires_at: float) -> None:
    _shared_claims[key] = expires_at
    _shared_claims.move_to_end(key)
    while len(_shared_claims) > MAX_SHARED_CLAIMS:
        _shared_claims.popitem(last=False)


async def _prune_shared(kv: Any, now: float, *, exclude_key: str) -> None:
    global _shared_claims_kv
    expired_keys: list[str] = []
    async with _shared_claims_lock:
        if _shared_claims_kv is not kv:
            _shared_claims.clear()
            _shared_claims_kv = kv
            return
        for candidate, expires_at in list(_shared_claims.items()):
            if expires_at > now:
                continue
            if candidate == exclude_key:
                _shared_claims.pop(candidate, None)
                continue
            _shared_claims.pop(candidate, None)
            expired_keys.append(candidate)
            if len(expired_keys) >= SHARED_PRUNE_BATCH:
                break

    if not expired_keys:
        return
    if not (callable(getattr(kv, "get", None)) and callable(getattr(kv, "delete", None))):
        return

    for stale_key in expired_keys:
        if not stale_key.startswith("nd."):
            continue
        try:
            stale_doc, stale_rev = await kv_get_json(kv, stale_key)
            if stale_doc is None or stale_rev <= 0:
                continue
            stale_expires = float(stale_doc.get("expires_at", 0))
            if stale_expires <= now:
                await kv.delete(stale_key, last=stale_rev)
            else:
                async with _shared_claims_lock:
                    if _shared_claims_kv is kv and stale_key not in _shared_claims:
                        _record_shared_claim_unlocked(stale_key, stale_expires)
        except Exception as exc:
            logger.debug("Notification dedup shared prune skipped for %s: %s", stale_key, exc)


async def _claim_shared(key: str, now: float) -> bool:
    global _shared_claims_kv
    kv = await _get_kv()
    if kv is None:
        return True
    await _prune_shared(kv, now, exclude_key=key)
    doc, rev = await kv_get_json(kv, key)
    if doc is not None and float(doc.get("expires_at", 0)) > now:
        return False
    expires_at = now + DEDUP_WINDOW_SECONDS
    claimed = await kv_cas_json(kv, key, {"expires_at": expires_at}, rev)
    if claimed:
        async with _shared_claims_lock:
            if _shared_claims_kv is not kv:
                _shared_claims.clear()
                _shared_claims_kv = kv
            _record_shared_claim_unlocked(key, expires_at)
    return claimed
