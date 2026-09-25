"""NATS KV leader election for single-runner jobs under multi-uvicorn workers."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

import nats
from nats.js.kv import KeyValue

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client, get_jetstream_context, get_or_create_kv_bucket
from app.nats.kv_cas import kv_cas_json, kv_get_json
from app.node.nats_memory import WORKER_ID
from app.utils.logger import get_logger
from config import nats_settings, runtime_settings, server_settings

logger = get_logger("nats-leader")

DEFAULT_LEASE_SECONDS = 15.0
HEARTBEAT_INTERVAL = 5.0
HEARTBEAT_MAX_RETRIES = 3
HEARTBEAT_RETRY_DELAY = 1.0
# Worst-case time from last successful renew to concede must stay under the lease.
assert HEARTBEAT_INTERVAL + (HEARTBEAT_MAX_RETRIES - 1) * HEARTBEAT_RETRY_DELAY < DEFAULT_LEASE_SECONDS

_nc: nats.NATS | None = None
_kv: KeyValue | None = None
_token: str | None = None
_heartbeat_task: asyncio.Task | None = None
_is_leader = False
_on_leadership_lost: list[Callable[[], Awaitable[None] | None]] = []


def leader_key() -> str:
    """Role-scoped lease key so split node/scheduler services do not fight each other.

    A single global key made the node role win leadership and skip APScheduler on the
    dedicated scheduler service (so on_hold→active / expire jobs never ran).
    """
    return f"job_leader.{runtime_settings.role.value}"


def needs_job_leader() -> bool:
    """Leader election is only needed when multiple uvicorn workers share one role."""
    return is_nats_enabled() and server_settings.workers > 1


def set_on_leadership_lost(callback: Callable[[], Awaitable[None] | None] | None) -> None:
    """Register a callback invoked when this process loses leadership at runtime.

    Composes with any previously registered callbacks instead of replacing them.
    Pass None to clear all registered callbacks.
    """
    global _on_leadership_lost
    if not _on_leadership_lost:
        _on_leadership_lost = []
    if callback is None:
        _on_leadership_lost.clear()
        return
    if callback not in _on_leadership_lost:
        _on_leadership_lost.append(callback)


async def _ensure_kv() -> KeyValue | None:
    global _nc, _kv
    if _kv is not None:
        return _kv
    if not is_nats_enabled():
        return None
    _nc = await create_nats_client()
    if _nc is None:
        return None
    js = await get_jetstream_context(_nc)
    _kv = await get_or_create_kv_bucket(js, nats_settings.scheduler_leader_kv_bucket)
    return _kv


def _lease_payload(token: str, expires_at: float) -> dict[str, Any]:
    return {"token": token, "worker_id": WORKER_ID, "expires_at": expires_at}


async def _concede_leadership(reason: str) -> None:
    """Mark leadership lost and pause scheduler/notification work via callback."""
    global _is_leader, _token
    if not _is_leader:
        _token = None
        return

    _is_leader = False
    _token = None
    logger.warning("Lost scheduler leadership: %s", reason)

    for callback in list(_on_leadership_lost or []):
        try:
            result = callback()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            logger.warning("Leadership lost callback failed: %s", exc)


async def try_become_leader(lease_seconds: float = DEFAULT_LEASE_SECONDS) -> bool:
    """Attempt to acquire the scheduler leader lease. Returns True if this process is leader."""
    global _token, _is_leader

    if not needs_job_leader():
        _is_leader = True
        return True

    kv = await _ensure_kv()
    if kv is None:
        logger.warning("Scheduler leader KV unavailable; refusing leadership under multi-worker")
        _is_leader = False
        return False

    token = uuid4().hex
    now = time.time()
    payload = _lease_payload(token, now + lease_seconds)

    try:
        if await kv_cas_json(kv, leader_key(), payload, 0):
            _token = token
            _is_leader = True
            return True
    except Exception as exc:
        # Key may already exist (or create raced); try read/steal before giving up.
        logger.debug("Scheduler leader create failed for key=%s, trying steal path: %s", leader_key(), exc)

    try:
        doc, rev = await kv_get_json(kv, leader_key())
    except Exception as exc:
        logger.warning("Failed to read scheduler leader key: %s", exc)
        _is_leader = False
        return False

    if doc is None or float(doc.get("expires_at", 0)) <= now:
        try:
            if await kv_cas_json(kv, leader_key(), payload, rev):
                _token = token
                _is_leader = True
                return True
        except Exception as exc:
            logger.warning("Failed to steal expired scheduler leader lease: %s", exc)

    _is_leader = False
    return False


async def _heartbeat_loop(lease_seconds: float = DEFAULT_LEASE_SECONDS) -> None:
    consecutive_failures = 0
    while _is_leader and _token is not None:
        # On renewal failure, retry promptly — do not wait another full HEARTBEAT_INTERVAL.
        delay = HEARTBEAT_INTERVAL if consecutive_failures == 0 else HEARTBEAT_RETRY_DELAY
        await asyncio.sleep(delay)
        kv = _kv
        token = _token
        if kv is None or token is None:
            await _concede_leadership("kv or token unavailable")
            return

        try:
            doc, rev = await kv_get_json(kv, leader_key())
            if doc is None:
                await _concede_leadership("lease key unavailable")
                return
            if doc.get("token") != token:
                await _concede_leadership("lease token invalid or replaced")
                return
            if not await kv_cas_json(kv, leader_key(), _lease_payload(token, time.time() + lease_seconds), rev):
                raise RuntimeError("failed to renew scheduler leader lease")
            consecutive_failures = 0
        except Exception as exc:
            consecutive_failures += 1
            logger.warning(
                "Scheduler leader heartbeat renewal failed (%s/%s): %s",
                consecutive_failures,
                HEARTBEAT_MAX_RETRIES,
                exc,
            )
            if consecutive_failures >= HEARTBEAT_MAX_RETRIES:
                await _concede_leadership("renewal exhausted")
                return


async def start_job_leader() -> bool:
    """Acquire leadership (or no-op when not needed) and start heartbeat."""
    global _heartbeat_task
    won = await try_become_leader()
    if won and needs_job_leader():
        if _heartbeat_task is None or _heartbeat_task.done():
            _heartbeat_task = asyncio.create_task(_heartbeat_loop())
        logger.info(
            "Acquired scheduler leadership (role=%s key=%s worker_id=%s)",
            runtime_settings.role.value,
            leader_key(),
            WORKER_ID,
        )
    elif won:
        logger.debug("Scheduler leadership not required; running jobs in this process")
    else:
        logger.debug(
            "Not scheduler leader; skipping APScheduler in this worker (role=%s key=%s)",
            runtime_settings.role.value,
            leader_key(),
        )
    return won


async def stop_job_leader() -> None:
    global _heartbeat_task, _token, _is_leader, _nc, _kv
    _is_leader = False
    if _heartbeat_task is not None:
        _heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _heartbeat_task
        _heartbeat_task = None

    if _kv is not None and _token is not None:
        key = leader_key()
        try:
            doc, rev = await kv_get_json(_kv, key)
            if doc is not None and doc.get("token") == _token:
                await _kv.delete(key, last=rev)
        except Exception as exc:
            logger.debug("Scheduler leader release failed for key=%s: %s", key, exc)

    _token = None
    if _nc is not None:
        await _nc.close()
    _nc = None
    _kv = None


def is_job_leader() -> bool:
    return _is_leader
