"""Drop duplicate notifications when every uvicorn worker observes the same event."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

from nats.js.errors import KeyWrongLastSequenceError

from app.nats import is_nats_enabled
from app.nats.kv_cas import kv_get_json
from app.utils.logger import get_logger
from config import server_settings

logger = get_logger("Notification")

DEDUP_WINDOW_SECONDS = 15.0
# A notification must not wait for dedup: nats-py applies the connect timeout to TCP, INFO and PONG each.
_CONNECT_TIMEOUT_SECONDS = 1
# For ws:// nats-py hands connect_timeout to aiohttp as the close timeout; the HTTP upgrade waits up to 300s.
_CONNECT_TOTAL_TIMEOUT_SECONDS = 3
_KV_TIMEOUT_SECONDS = 1.5
# After a failure, send without the shared check for a while instead of waiting on NATS every time.
_RETRY_AFTER_SECONDS = 20.0
_local_claims: dict[str, float] = {}
_local_lock = asyncio.Lock()
_kv = None
_nc = None
_kv_lock = asyncio.Lock()
_closed = False
_retry_at = 0.0


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


def _kv_ready() -> bool:
    # Rebuild only after the client is closed for good; a reconnecting client is not connected but still usable.
    return _kv is not None and _nc is not None and not _nc.is_closed


def _backing_off() -> bool:
    return time.monotonic() < _retry_at


def _back_off() -> None:
    global _retry_at
    _retry_at = time.monotonic() + _RETRY_AFTER_SECONDS


async def _log_nats_error(exc: Exception) -> None:
    # The nats-py default logs a traceback for every failed attempt.
    logger.debug("Notification dedup NATS error: %s", exc)


async def _get_kv():
    global _kv, _nc
    if _closed or _backing_off():
        return None
    if _kv_ready():
        return _kv
    # Notifications that arrive during a connect wait for it (bounded) so they still get the shared check.
    async with _kv_lock:
        # The connect they waited for may have failed: do not try again for every queued notification.
        if _closed or _backing_off():
            return None
        if _kv_ready():
            return _kv
        from app.nats.client import get_jetstream_context, get_or_create_kv_bucket
        from config import nats_settings

        _kv = _nc = None
        try:
            nc = await _connect_nats()
        except BaseException:
            _back_off()
            raise
        try:
            js = await get_jetstream_context(nc)
            kv = await asyncio.wait_for(
                get_or_create_kv_bucket(js, nats_settings.scheduler_leader_kv_bucket),
                timeout=_KV_TIMEOUT_SECONDS,
            )
        except BaseException:
            _back_off()
            await _close_nats(nc)
            raise
        # Shutdown may have run while connect() was retrying; nobody would close this client later.
        if kv is None or _closed:
            await _close_nats(nc)
            return None
        _nc, _kv = nc, kv
        return _kv


async def _connect_nats():
    import nats

    from app.nats import get_nats_config

    nc = nats.NATS()
    try:
        # Bounded connect: without allow_reconnect nats-py still tries TCP max_reconnect_attempts + 1 times
        # (0 would mean forever); a failure after TCP (INFO, PONG, auth, TLS) is raised at once.
        # Without reconnects a lost client closes and is rebuilt by _get_kv().
        await asyncio.wait_for(
            nc.connect(
                get_nats_config()["url"],
                allow_reconnect=False,
                max_reconnect_attempts=1,
                reconnect_time_wait=0,
                connect_timeout=_CONNECT_TIMEOUT_SECONDS,
                error_cb=_log_nats_error,
            ),
            timeout=_CONNECT_TOTAL_TIMEOUT_SECONDS,
        )
    except BaseException:
        # nats-py leaves the socket of a failed handshake open.
        await _close_nats(nc)
        raise
    return nc


async def _close_nats(nc) -> None:
    # Bounded: the callers hold _kv_lock, and every notification would queue behind a stuck close.
    try:
        await asyncio.wait_for(nc.close(), timeout=_CONNECT_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.debug("Failed to close notification dedup NATS connection: %s", exc)


async def close_notification_dedup() -> None:
    global _kv, _nc, _closed
    # Skip _kv_lock: a notification may hold it while connect() retries an unreachable server for minutes.
    _closed = True
    nc, _nc, _kv = _nc, None, None
    if nc is None:
        return
    try:
        await asyncio.wait_for(nc.close(), timeout=3)
    except Exception as exc:
        logger.debug("Failed to close notification dedup NATS connection: %s", exc)


async def _claim_shared(key: str, now: float) -> bool:
    kv = await _get_kv()
    if kv is None:
        return True
    try:
        return await asyncio.wait_for(_claim_in_kv(kv, key, now), timeout=_KV_TIMEOUT_SECONDS)
    except Exception:
        _back_off()
        raise


async def _claim_in_kv(kv, key: str, now: float) -> bool:
    # A lost CAS is not proof of a duplicate: the expired key may have been removed under us.
    # Only a live claim by another worker that we have read drops the notification.
    for _ in range(2):
        doc, rev = await kv_get_json(kv, key)
        if _is_live(doc, now):
            return False
        if await _write_claim(kv, key, now, rev):
            return True
    doc, _ = await kv_get_json(kv, key)
    return not _is_live(doc, now)


def _is_live(doc: dict[str, Any] | None, now: float) -> bool:
    return doc is not None and float(doc.get("expires_at", 0)) > now


async def _write_claim(kv, key: str, now: float, revision: int) -> bool:
    # Unlike kv_cas_json, only a lost race returns False: a failed write raises so _claim_shared backs off.
    payload = json.dumps({"expires_at": now + DEDUP_WINDOW_SECONDS}, separators=(",", ":")).encode()
    try:
        if revision == 0:
            await kv.create(key, payload)
        else:
            await kv.update(key, payload, last=revision)
    except KeyWrongLastSequenceError:
        return False
    return True
