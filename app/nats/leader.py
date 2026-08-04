"""NATS KV leader election for single-runner jobs under multi-uvicorn workers."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from uuid import uuid4

import nats
import nats.js.errors as nats_js_errors
from nats.js.kv import KeyValue

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client, get_jetstream_context, get_or_create_kv_bucket
from app.node.nats_memory import WORKER_ID
from app.utils.logger import get_logger
from config import nats_settings, server_settings

logger = get_logger("nats-leader")

LEADER_KEY = "scheduler_leader"
DEFAULT_LEASE_SECONDS = 15.0
HEARTBEAT_INTERVAL = 5.0

_nc: nats.NATS | None = None
_kv: KeyValue | None = None
_token: str | None = None
_heartbeat_task: asyncio.Task | None = None
_is_leader = False


def needs_job_leader() -> bool:
    """Leader election is only needed when multiple uvicorn workers share one role."""
    return is_nats_enabled() and server_settings.workers > 1


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


def _payload(token: str, expires_at: float) -> bytes:
    return json.dumps(
        {"token": token, "worker_id": WORKER_ID, "expires_at": expires_at}, separators=(",", ":")
    ).encode()


def _parse(raw: bytes | None) -> tuple[str, float] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return str(data["token"]), float(data["expires_at"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None


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
    payload = _payload(token, now + lease_seconds)

    try:
        await kv.create(LEADER_KEY, payload)
        _token = token
        _is_leader = True
        return True
    except nats_js_errors.KeyWrongLastSequenceError as exc:
        logger.debug("Scheduler leader create CAS conflict for key=%s: %s", LEADER_KEY, exc)
    except Exception as exc:
        logger.warning("Failed to create scheduler leader key: %s", exc)
        _is_leader = False
        return False

    try:
        entry = await kv.get(LEADER_KEY)
    except (nats_js_errors.KeyNotFoundError, nats_js_errors.KeyDeletedError) as exc:
        logger.debug("Scheduler leader key miss for key=%s: %s", LEADER_KEY, exc)
        _is_leader = False
        return False
    except Exception as exc:
        logger.warning("Failed to read scheduler leader key: %s", exc)
        _is_leader = False
        return False

    info = _parse(entry.value)
    if info is None or info[1] <= now:
        try:
            await kv.update(LEADER_KEY, payload, last=entry.revision)
            _token = token
            _is_leader = True
            return True
        except nats_js_errors.KeyWrongLastSequenceError as exc:
            logger.debug(
                "Scheduler leader steal CAS conflict for key=%s revision=%s: %s",
                LEADER_KEY,
                entry.revision,
                exc,
            )
        except Exception as exc:
            logger.warning("Failed to steal expired scheduler leader lease: %s", exc)

    _is_leader = False
    return False


async def _heartbeat_loop(lease_seconds: float = DEFAULT_LEASE_SECONDS) -> None:
    global _is_leader
    while _is_leader and _token is not None:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        kv = _kv
        if kv is None or _token is None:
            _is_leader = False
            return
        try:
            entry = await kv.get(LEADER_KEY)
            info = _parse(entry.value)
            if info is None or info[0] != _token:
                logger.warning("Lost scheduler leadership")
                _is_leader = False
                return
            await kv.update(LEADER_KEY, _payload(_token, time.time() + lease_seconds), last=entry.revision)
        except Exception as exc:
            logger.warning("Scheduler leader heartbeat failed: %s", exc)
            _is_leader = False
            return


async def start_job_leader() -> bool:
    """Acquire leadership (or no-op when not needed) and start heartbeat."""
    global _heartbeat_task
    won = await try_become_leader()
    if won and needs_job_leader():
        _heartbeat_task = asyncio.create_task(_heartbeat_loop())
        logger.info("Acquired scheduler leadership (worker_id=%s)", WORKER_ID)
    elif won:
        logger.debug("Scheduler leadership not required; running jobs in this process")
    else:
        logger.info("Not scheduler leader; skipping APScheduler in this worker")
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
        try:
            entry = await _kv.get(LEADER_KEY)
            info = _parse(entry.value)
            if info and info[0] == _token:
                await _kv.delete(LEADER_KEY, last=entry.revision)
        except Exception as exc:
            logger.debug("Scheduler leader release failed for key=%s: %s", LEADER_KEY, exc)

    _token = None
    if _nc is not None:
        await _nc.close()
    _nc = None
    _kv = None


def is_job_leader() -> bool:
    return _is_leader
