"""Drop duplicate notifications when every uvicorn worker observes the same event."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

from nats.js.errors import BucketNotFoundError, KeyWrongLastSequenceError

from app import on_shutdown
from app.nats import is_nats_enabled
from app.nats.client import create_nats_client, get_or_create_kv_bucket
from app.nats.kv_cas import kv_get_json
from app.nats.kv_watch import watch_kv
from app.utils.logger import get_logger
from config import nats_settings, server_settings

logger = get_logger("Notification")

DEDUP_WINDOW_SECONDS = 15.0
_SHARED_EVENTS = {"connect_node", "recovered_node", "error_node", "limited_node"}
_local_claims: dict[str, float] = {}
_local_lock = asyncio.Lock()
_kv = None
_nc = None
_kv_lock = asyncio.Lock()


def notification_fingerprint(event_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Only the same observed node transition, not two independent edits, is duplicate."""

    def serialize(value):
        if hasattr(value, "model_dump"):
            return {
                "value": value.model_dump(mode="json"),
                "event_id": getattr(value, "event_id", None),
            }
        if hasattr(value, "__dict__"):
            return vars(value)
        return str(value)

    raw = json.dumps([event_name, args, kwargs], sort_keys=True, default=serialize).encode()
    return "nd." + hashlib.sha256(raw).hexdigest()


async def claim_notification_slot(event_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool:
    """Return True if this worker should emit the notification."""
    if server_settings.workers <= 1 or event_name not in _SHARED_EVENTS:
        return True

    key = notification_fingerprint(event_name, args, kwargs)
    now = time.time()
    async with _local_lock:
        _prune_local(now)
        expires_at = _local_claims.get(key, 0)
        if expires_at > now:
            logger.debug("Skipping duplicate notification %s (%s)", event_name, key)
            return False

    if not is_nats_enabled():
        async with _local_lock:
            _local_claims[key] = now + DEDUP_WINDOW_SECONDS
        return True

    try:
        if not await _claim_shared(key, now):
            logger.debug("Skipping duplicate notification %s claimed by another worker (%s)", event_name, key)
            return False
    except Exception as exc:
        logger.debug("Notification dedup store unavailable for %s: %s", event_name, exc)
    async with _local_lock:
        _local_claims[key] = time.time() + DEDUP_WINDOW_SECONDS
    return True


def _prune_local(now: float) -> None:
    expired = [key for key, expires_at in _local_claims.items() if expires_at <= now]
    for key in expired:
        del _local_claims[key]


async def _get_kv():
    """Dedup entries expire physically in their own bounded bucket, never the leader bucket."""
    global _kv, _nc
    if _nc is not None and _nc.is_closed:
        _nc = _kv = None
    if _kv is not None:
        return _kv
    async with _kv_lock:
        if _kv is None:
            if _nc is None or _nc.is_closed:
                _nc = await create_nats_client()
            if _nc is None:
                return None
            _kv = await get_or_create_kv_bucket(
                _nc.jetstream(),
                f"{nats_settings.scheduler_leader_kv_bucket}_notifications",
                ttl=DEDUP_WINDOW_SECONDS,
                max_bytes=8 * 1024 * 1024,
            )
        return _kv


async def _claim_shared(key: str, now: float) -> bool:
    kv = await _get_kv()
    if kv is None:
        return True
    doc, revision = await kv_get_json(kv, key)
    # Connecting or reading can consume the entire dedup window during an
    # outage. Start the claim window only once the store is reachable.
    now = time.time()
    if doc is not None and float(doc.get("expires_at", 0)) > now:
        return False
    payload = json.dumps({"expires_at": now + DEDUP_WINDOW_SECONDS}).encode()
    try:
        if revision:
            await kv.update(key, payload, last=revision)
        else:
            await kv.create(key, payload)
    except KeyWrongLastSequenceError:
        return False
    return True


@on_shutdown
async def close_notification_dedup() -> None:
    global _nc, _kv
    if _nc is not None:
        await _nc.close()
    _nc = _kv = None
    _local_claims.clear()


async def cleanup_legacy_notification_claims(js) -> int:
    """Incrementally remove expired pre-upgrade claims without touching leader leases."""
    bucket = nats_settings.scheduler_leader_kv_bucket
    try:
        kv = await js.key_value(bucket)
    except BucketNotFoundError:
        return 0
    watcher = await watch_kv(kv, "nd.*", ignore_deletes=True, inactive_threshold=5, snapshot_only=True)
    expired = []
    try:
        async for entry in watcher:
            if entry is None:
                break
            doc, revision = await kv_get_json(kv, entry.key)
            if doc is None:
                continue
            try:
                expires_at = float(doc.get("expires_at", 0))
            except ValueError, TypeError:
                continue
            if expires_at <= time.time():
                expired.append((entry.key, revision))
                if len(expired) >= 100:
                    break
    finally:
        await watcher.stop()
    for key, revision in expired:
        # New writes always have a higher revision and survive this cutoff.
        await js.purge_stream(f"KV_{bucket}", subject=f"$KV.{bucket}.{key}", seq=revision + 1)
    return len(expired)
