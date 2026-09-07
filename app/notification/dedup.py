"""Drop duplicate notifications when every uvicorn worker observes the same event."""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

from app.nats import is_nats_enabled
from app.nats.kv_cas import kv_cas_json, kv_get_json
from app.utils.logger import get_logger

logger = get_logger("Notification")

DEDUP_WINDOW_SECONDS = 15.0
_local_claims: dict[str, float] = {}
_local_lock = asyncio.Lock()
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


async def _get_kv():
    global _kv
    if _kv is not None:
        return _kv
    async with _kv_lock:
        if _kv is not None:
            return _kv
        from app.nats.client import setup_nats_kv
        from config import nats_settings

        _, _, kv = await setup_nats_kv(nats_settings.scheduler_leader_kv_bucket)
        _kv = kv
        return _kv


async def _claim_shared(key: str, now: float) -> bool:
    kv = await _get_kv()
    if kv is None:
        return True
    doc, rev = await kv_get_json(kv, key)
    if doc is not None and float(doc.get("expires_at", 0)) > now:
        return False
    return await kv_cas_json(kv, key, {"expires_at": now + DEDUP_WINDOW_SECONDS}, rev)
