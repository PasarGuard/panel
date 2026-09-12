"""Remove old queue tombstones without deleting concurrently recreated keys."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime

from nats.js.client import JetStreamContext
from nats.js.errors import BucketNotFoundError

from app.nats.kv_watch import watch_kv


@dataclass
class _DeletedPrefix:
    protected: bool = False
    revision: int = 0
    count: int = 0


async def compact_deleted_keys(js: JetStreamContext, bucket: str, *, older_than: float = 300) -> int:
    try:
        kv = await js.key_value(bucket)
    except BucketNotFoundError:
        return 0
    watcher = await watch_kv(kv, ">", inactive_threshold=5, snapshot_only=True)
    cutoff = datetime.now(UTC).timestamp() - older_than
    prefixes: dict[str, _DeletedPrefix] = {}
    individual: list[tuple[str, int]] = []
    previous_revision = 0
    complete = False
    purged = 0
    try:
        async for entry in watcher:
            if entry is None:
                complete = True
                break
            # LAST_PER_SUBJECT snapshots arrive in stream revision order.
            # A broken snapshot must never authorize a broad purge.
            if entry.revision <= previous_revision:
                raise RuntimeError("Unordered node-sync compaction snapshot")
            previous_revision = entry.revision
            parent, separator, _ = entry.key.rpartition(".")
            pattern = parent + ".*" if separator else entry.key
            prefix = prefixes.setdefault(pattern, _DeletedPrefix())
            if entry.operation not in ("DEL", "PURGE") or entry.created.timestamp() > cutoff:
                prefix.protected = True
            elif not prefix.protected:
                prefix.revision = entry.revision
                prefix.count += 1
            elif len(individual) < 1024:
                # Live work can precede other old tombstones. Bound the slower
                # per-key fallback; later intervals continue where it left off.
                individual.append((entry.key, entry.revision))
    finally:
        with contextlib.suppress(Exception):
            await watcher.stop()

    if not complete:
        raise RuntimeError("Incomplete node-sync compaction snapshot")
    for pattern, prefix in prefixes.items():
        if prefix.count:
            # All earlier current entries in this disjoint key family were
            # expired tombstones. One request removes that whole prefix of
            # history. Concurrent writes always have a higher revision.
            await js.purge_stream(f"KV_{bucket}", subject=f"$KV.{bucket}.{pattern}", seq=prefix.revision + 1)
            purged += prefix.count
    for key, revision in individual:
        await js.purge_stream(f"KV_{bucket}", subject=f"$KV.{bucket}.{key}", seq=revision + 1)
        purged += 1
    return purged
