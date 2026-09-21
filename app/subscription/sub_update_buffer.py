"""Buffer public subscription-update writes so GET /sub stays read-mostly.

Each process keeps an in-memory queue and flushes on size, a short interval
(every worker — APScheduler is leader-only), shutdown, and before admin reads.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime as dt
from typing import Any

from sqlalchemy import insert, select

from app.db import GetDB
from app.db.models import User, UserSubscriptionUpdate
from app.lifecycle import on_shutdown, on_startup
from app.utils.logger import get_logger
from config import runtime_settings

logger = get_logger("sub-update-buffer")

FLUSH_INTERVAL_SECONDS = 2.0
FLUSH_BATCH_SIZE = 100
_MAX_BUFFER = 50_000

_USER_AGENT_MAX_LEN = UserSubscriptionUpdate.__table__.columns.user_agent.type.length or 512
_IP_MAX_LEN = UserSubscriptionUpdate.__table__.columns.ip.type.length or 64
_HWID_MAX_LEN = UserSubscriptionUpdate.__table__.columns.hwid.type.length or 256

_pending: list[dict[str, Any]] = []
_lock = asyncio.Lock()
_drain_lock = asyncio.Lock()
_flush_task: asyncio.Task | None = None


def _sanitize_record(user_id: int, user_agent: str, ip: str | None, hwid: str | None) -> dict[str, Any]:
    sanitized_ip = (ip or "")[:_IP_MAX_LEN] or None
    sanitized_hwid = (hwid or "")[:_HWID_MAX_LEN] or None
    return {
        "user_id": user_id,
        "user_agent": (user_agent or "")[:_USER_AGENT_MAX_LEN],
        "ip": sanitized_ip,
        "hwid": sanitized_hwid,
        "created_at": dt.now(UTC),
    }


def pending_count() -> int:
    return len(_pending)


async def reset_user_sub_update_buffer() -> None:
    """Drop queued rows without writing. Tests only."""
    async with _lock:
        _pending.clear()


async def queue_user_sub_update(user_id: int, user_agent: str, ip: str | None = None, hwid: str | None = None) -> None:
    """Enqueue a subscription-update row; may kick a background flush."""
    record = _sanitize_record(user_id, user_agent, ip, hwid)
    should_flush = False
    dropped = 0
    async with _lock:
        prev = len(_pending)
        _pending.append(record)
        overflow = len(_pending) - _MAX_BUFFER
        if overflow > 0:
            del _pending[:overflow]
            dropped = overflow
        should_flush = prev < FLUSH_BATCH_SIZE <= len(_pending)
    if dropped:
        logger.warning("Dropped %s buffered subscription updates; buffer full", dropped)
    if should_flush:
        asyncio.create_task(flush_user_sub_updates(), name="sub_update_flush")


async def flush_user_sub_updates() -> int:
    """Persist queued rows. Concurrent callers wait, then drain anything left."""
    async with _drain_lock:
        written = 0
        while True:
            async with _lock:
                if not _pending:
                    return written
                batch = _pending[:FLUSH_BATCH_SIZE]
                del _pending[:FLUSH_BATCH_SIZE]
            try:
                async with GetDB() as db:
                    # Users can be deleted after their subscription request was queued.
                    # Lock surviving parents until commit so concurrent deletes cannot
                    # invalidate the foreign keys between this read and the insert.
                    user_ids = sorted({record["user_id"] for record in batch})
                    existing_user_ids = set(
                        await db.scalars(
                            select(User.id)
                            .where(User.id.in_(user_ids))
                            .order_by(User.id)
                            .with_for_update(read=True, key_share=True)
                        )
                    )
                    live_records = [record for record in batch if record["user_id"] in existing_user_ids]
                    if live_records:
                        await db.execute(insert(UserSubscriptionUpdate.__table__), live_records)
                    await db.commit()
                written += len(live_records)
            except Exception:
                async with _lock:
                    _pending[0:0] = batch
                    overflow = len(_pending) - _MAX_BUFFER
                    if overflow > 0:
                        del _pending[:overflow]
                logger.exception("Failed to flush %s buffered subscription updates", len(batch))
                raise


async def _flush_loop() -> None:
    while True:
        await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
        try:
            await flush_user_sub_updates()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic subscription-update flush failed")


@on_startup
async def start_sub_update_flusher() -> None:
    global _flush_task
    if not runtime_settings.role.runs_panel:
        return
    if _flush_task is not None and not _flush_task.done():
        return
    _flush_task = asyncio.create_task(_flush_loop(), name="sub_update_flush_loop")


@on_shutdown
async def stop_sub_update_flusher() -> None:
    global _flush_task
    if _flush_task is not None:
        _flush_task.cancel()
        try:
            await _flush_task
        except asyncio.CancelledError:
            pass
        _flush_task = None
    try:
        await flush_user_sub_updates()
    except Exception:
        logger.exception("Final subscription-update flush failed")
