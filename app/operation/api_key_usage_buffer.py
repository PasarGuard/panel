"""Buffer request_count increments for API keys without max_requests.

For an unlimited key the counter is only a statistic, yet the atomic
per-request UPDATE serialises every request of that key on one row lock.
Such requests are counted in memory and added to the row on a short
interval and at shutdown. Keys with a limit never use this buffer: they keep
the atomic conditional UPDATE, so the limit holds across processes.

Each process has its own buffer, so the stored counter lags by up to
FLUSH_INTERVAL_SECONDS, and a crashed process loses its unflushed requests.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import update

from app.db import GetDB
from app.db.models import APIKey
from app.lifecycle import on_shutdown, on_startup
from app.utils.logger import get_logger
from config import runtime_settings

logger = get_logger("api-key-usage-buffer")

FLUSH_INTERVAL_SECONDS = 5.0

# Keyed by (id, key_hash): a revoked key gets a new hash and its counter is reset,
# and SQLite may give a deleted key's id to a new key; neither must inherit old requests.
_pending: dict[tuple[int, str], int] = {}
_drain_lock = asyncio.Lock()
_flush_task: asyncio.Task | None = None


def record_api_key_usage(key_id: int, key_hash: str) -> None:
    """Count one request of an unlimited key in memory."""
    _pending[(key_id, key_hash)] = _pending.get((key_id, key_hash), 0) + 1


def take_api_key_usage(key_id: int, key_hash: str) -> int:
    """Remove and return this process's unflushed requests for one key."""
    return _pending.pop((key_id, key_hash), 0)


def restore_api_key_usage(key_id: int, key_hash: str, count: int) -> None:
    """Put back requests that could not be written."""
    if count > 0:
        _pending[(key_id, key_hash)] = _pending.get((key_id, key_hash), 0) + count


def pending_api_key_usage(key_id: int) -> int:
    return sum(count for (pending_id, _), count in _pending.items() if pending_id == key_id)


def reset_api_key_usage_buffer() -> None:
    """Drop unflushed requests without writing. Tests only."""
    _pending.clear()


async def flush_api_key_usage() -> int:
    """Add buffered requests to request_count; returns how many were written.

    The increment is unconditional: the requests were served while the key
    had no limit, so they count even if a limit was set since. Keys deleted
    or revoked in the meantime match no row and are skipped.
    """
    async with _drain_lock:
        if not _pending:
            return 0
        batch = dict(_pending)
        _pending.clear()
        unwritten = dict(batch)
        try:
            async with GetDB() as db:
                # One short transaction per key: holding several row locks at once
                # could deadlock with a bulk delete of keys.
                for key_id, key_hash in sorted(batch):
                    await db.execute(
                        update(APIKey)
                        .where(APIKey.id == key_id, APIKey.key_hash == key_hash)
                        .values(request_count=APIKey.request_count + batch[(key_id, key_hash)])
                    )
                    await db.commit()
                    del unwritten[(key_id, key_hash)]
        except Exception:
            for (key_id, key_hash), count in unwritten.items():
                restore_api_key_usage(key_id, key_hash, count)
            logger.exception("Failed to flush buffered API key usage for %s key(s)", len(unwritten))
            raise
        return sum(batch.values())


async def _flush_loop() -> None:
    while True:
        await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
        try:
            # Shielded: a shutdown that cancels the loop mid-flush must not drop the batch
            # already taken out of the buffer; the final flush waits for it on the lock.
            await asyncio.shield(flush_api_key_usage())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic API key usage flush failed")


@on_startup
async def start_api_key_usage_flusher() -> None:
    global _flush_task
    if not runtime_settings.role.runs_panel:
        return
    if _flush_task is not None and not _flush_task.done():
        return
    _flush_task = asyncio.create_task(_flush_loop(), name="api_key_usage_flush_loop")


@on_shutdown
async def stop_api_key_usage_flusher() -> None:
    global _flush_task
    if _flush_task is not None:
        _flush_task.cancel()
        try:
            await _flush_task
        except asyncio.CancelledError:
            pass
        _flush_task = None
    try:
        await flush_api_key_usage()
    except Exception:
        logger.exception("Final API key usage flush failed")
