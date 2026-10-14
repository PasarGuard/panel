"""Persistent per-node recovery requests for exhausted user commands."""

import asyncio

from nats.js.errors import APIError, KeyDeletedError, KeyNotFoundError, KeyWrongLastSequenceError

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client, get_or_create_kv_bucket
from config import nats_settings

_nc = None
_kv = None
_lock = asyncio.Lock()


def recovery_bucket() -> str:
    """Keep recovery markers in the configured node-sync namespace."""
    return f"{nats_settings.node_user_sync_kv_bucket}_recovery"


async def _get_recovery_kv():
    """Reuse a dedicated connection for health-check recovery requests."""
    global _nc, _kv
    if not is_nats_enabled():
        return None
    async with _lock:
        if _nc is None or _nc.is_closed:
            _nc = await create_nats_client()
            _kv = None
        if _kv is None:
            _kv = await get_or_create_kv_bucket(_nc.jetstream(), recovery_bucket())
        return _kv


async def request_node_reconciliation(js, node_ids: list[int]) -> None:
    """Durably coalesce failed commands into a fresh snapshot request per node."""
    if not node_ids:
        return
    kv = await get_or_create_kv_bucket(js, recovery_bucket())
    for node_id in dict.fromkeys(node_ids):
        await kv.put(f"n.{node_id}", b"reconcile")


async def node_reconciliation_revision(node_id: int) -> int | None:
    """Return the revision that a completed snapshot may safely retire."""
    kv = await _get_recovery_kv()
    if kv is None:
        return None
    try:
        return (await kv.get(f"n.{node_id}")).revision
    except KeyDeletedError, KeyNotFoundError:
        return None


async def complete_node_reconciliation(node_id: int, revision: int | None) -> None:
    """Clear only the request captured before the snapshot; preserve newer requests."""
    if revision is None:
        return
    kv = await _get_recovery_kv()
    if kv is None:
        raise RuntimeError("NATS is unavailable for node reconciliation")
    try:
        await kv.delete(f"n.{node_id}", last=revision)
    except APIError as exc:
        if not isinstance(exc, KeyWrongLastSequenceError) and exc.err_code != 10071:
            raise


async def shutdown_node_recovery() -> None:
    """Close the process's health-check connection without deleting durable markers."""
    global _nc, _kv
    if _nc is not None:
        await _nc.close()
    _nc = _kv = None
