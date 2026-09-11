"""Remove old queue tombstones without deleting concurrently recreated keys."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from nats.js.client import JetStreamContext
from nats.js.errors import BucketNotFoundError


async def compact_deleted_keys(js: JetStreamContext, bucket: str, *, older_than: float = 300) -> int:
    try:
        kv = await js.key_value(bucket)
    except BucketNotFoundError:
        return 0
    watcher = await kv.watch(">", meta_only=True, inactive_threshold=5)
    cutoff = datetime.now(UTC).timestamp() - older_than
    purged = 0
    try:
        async for entry in watcher:
            if entry is None:
                break
            if entry.operation not in ("DEL", "PURGE") or entry.created.timestamp() > cutoff:
                continue
            # A key can be recreated after this snapshot. Purge ONLY revisions
            # up to the observed tombstone, never the newer pending update.
            await js.purge_stream(f"KV_{bucket}", subject=f"$KV.{bucket}.{entry.key}", seq=entry.revision + 1)
            purged += 1
    finally:
        with contextlib.suppress(Exception):
            await watcher.stop()
    return purged
