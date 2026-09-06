"""Revision compare-and-set helpers for NATS JetStream KV (and test doubles)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
from typing import Any, Protocol

import nats.errors as nats_errors
import nats.js.errors as nats_js_errors
from nats.js.kv import KeyValue

from app.utils.logger import get_logger

logger = get_logger("nats-kv-cas")

_CAS_RETRY_BASE_DELAY = 0.01


async def cas_retry_backoff() -> None:
    """Small jittered delay between CAS retry attempts to avoid hammering NATS under contention."""
    await asyncio.sleep(_CAS_RETRY_BASE_DELAY * (1 + random.random()))


class CasKv(Protocol):
    async def get(self, key: str) -> Any: ...

    async def create(self, key: str, value: bytes) -> int: ...

    async def update(self, key: str, value: bytes, last: int | None = None) -> int: ...

    async def delete(self, key: str, last: int | None = None) -> bool: ...

    async def keys(self, filters: list[str] | None = None) -> list[str]: ...


async def kv_get_json(kv: CasKv, key: str) -> tuple[dict[str, Any] | None, int]:
    try:
        entry = await kv.get(key)
    except (nats_js_errors.KeyNotFoundError, nats_js_errors.KeyDeletedError) as exc:
        logger.debug("NATS KV miss for key=%s: %s", key, exc)
        return None, 0
    if not entry or not entry.value:
        return None, getattr(entry, "revision", 0) or 0
    return json.loads(entry.value), entry.revision


async def kv_cas_json(kv: CasKv, key: str, value: dict[str, Any], revision: int) -> bool:
    payload = json.dumps(value, separators=(",", ":")).encode()
    try:
        if revision == 0:
            await kv.create(key, payload)
        else:
            await kv.update(key, payload, last=revision)
        return True
    except nats_errors.Error as exc:
        logger.debug("NATS KV CAS attempt failed for key=%s revision=%s: %s", key, revision, exc)
        return False


async def kv_put_json(kv: CasKv, key: str, value: dict[str, Any]) -> None:
    """Upsert JSON with CAS retries (latest value wins)."""
    for attempt in range(32):
        _, rev = await kv_get_json(kv, key)
        if await kv_cas_json(kv, key, value, rev):
            return
        if attempt < 31:
            await cas_retry_backoff()
    raise RuntimeError(f"failed to put NATS KV key={key} after CAS retries")


async def kv_list_keys(kv: CasKv, prefix: str) -> list[str]:
    # kv.keys() always watches the entire bucket ("watch('>')") and only filters
    # client-side, even when passed a `filters` argument. With many nodes sharing
    # one bucket that means every call streams every key in the whole bucket to
    # every caller, which floods NATS ("Slow Consumer" / consumer_info timeouts)
    # as the number of nodes and pending/claimed users grows. Real KV objects
    # support watch(), whose `keys` argument becomes the JetStream consumer's
    # filter subject, so use that to filter server-side to this prefix only.
    watch = getattr(kv, "watch", None)
    if callable(watch):
        watcher = await watch(f"{prefix}*", ignore_deletes=True, meta_only=True)
        try:
            keys: list[str] = []
            async for entry in watcher:
                if entry is None:
                    break
                keys.append(entry.key)
            return keys
        finally:
            with contextlib.suppress(Exception):
                await watcher.stop()

    try:
        keys = await kv.keys()
    except nats_js_errors.NoKeysError:
        return []
    return [key for key in keys if key.startswith(prefix)]


class MemoryCasKv:
    """In-process KV with revision CAS for unit tests / demos."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[bytes, int]] = {}
        self._rev = 0

    async def get(self, key: str) -> KeyValue.Entry:
        if key not in self._data:
            raise nats_js_errors.KeyNotFoundError
        value, revision = self._data[key]
        return KeyValue.Entry(
            bucket="",
            key=key,
            value=value,
            revision=revision,
            delta=0,
            created=None,
            operation=None,
        )

    async def create(self, key: str, value: bytes) -> int:
        if key in self._data:
            raise nats_js_errors.KeyWrongLastSequenceError("wrong last sequence")
        self._rev += 1
        self._data[key] = (value, self._rev)
        return self._rev

    async def update(self, key: str, value: bytes, last: int | None = None) -> int:
        current = self._data.get(key)
        if current is None:
            raise nats_js_errors.KeyWrongLastSequenceError("wrong last sequence")
        _, revision = current
        if last is not None and revision != last:
            raise nats_js_errors.KeyWrongLastSequenceError("wrong last sequence")
        self._rev += 1
        self._data[key] = (value, self._rev)
        return self._rev

    async def delete(self, key: str, last: int | None = None) -> bool:
        current = self._data.get(key)
        if current is None:
            return False
        _, revision = current
        if last is not None and revision != last:
            raise nats_js_errors.KeyWrongLastSequenceError("wrong last sequence")
        del self._data[key]
        return True

    async def keys(self, filters: list[str] | None = None) -> list[str]:
        keys = list(self._data)
        if not filters:
            if not keys:
                raise nats_js_errors.NoKeysError
            return keys
        matched = [key for key in keys if any(f in key for f in filters)]
        if not matched:
            raise nats_js_errors.NoKeysError
        return matched
