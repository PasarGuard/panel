"""A live key-only index for the shared node sync queue.

KV values and CAS revisions still come from JetStream. The index only discovers
candidate keys, so a delayed notification cannot grant ownership of a user.
"""

from __future__ import annotations

import asyncio
import contextlib

from app.nats.kv_cas import CasKv, kv_list_keys
from app.nats.kv_watch import watch_kv
from app.utils.logger import get_logger

logger = get_logger("nats-kv-index")


class KvKeyIndex:
    SNAPSHOT_STALL_TIMEOUT = 30

    def __init__(self, kv: CasKv):
        self._kv = kv
        self._keys: dict[str, dict[str, int]] = {}
        self._local_puts: dict[str, int] = {}
        self._last_revision = 0
        self._ready = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._closed = False

    async def entries(self, prefix: str) -> dict[str, int]:
        if self._closed:
            raise RuntimeError("NATS key index is closed")
        if not callable(getattr(self._kv, "watch", None)):
            return dict.fromkeys(await kv_list_keys(self._kv, prefix), 0)
        if self._task is None:
            # No await between checking and setting: all node callers share one
            # watcher per process, including concurrent first-time callers.
            self._task = asyncio.create_task(self._run(), name="node-sync-key-index")
        while not self._ready.is_set():
            revision = self._last_revision
            try:
                async with asyncio.timeout(self.SNAPSHOT_STALL_TIMEOUT):
                    await self._ready.wait()
            except TimeoutError:
                # Large snapshots can take longer than one timeout interval.
                # Fail only when replay has stopped making progress.
                if self._last_revision <= revision:
                    raise
        if self._closed:
            raise RuntimeError("NATS key index is closed")
        return dict(self._keys.get(prefix, {}))

    async def keys(self, prefix: str) -> list[str]:
        return list(await self.entries(prefix))

    async def snapshot(self, prefixes: tuple[str, ...]) -> tuple[set[str], int]:
        """Copy candidate keys and their replay checkpoint without yielding."""
        await self.entries(prefixes[0])
        return {key for prefix in prefixes for key in self._keys.get(prefix, {})}, self._last_revision

    def observe_put(self, key: str, revision: int) -> None:
        """Expose an acknowledged local write before its watch event arrives.

        The bridge can exit its lazy sync loop on an empty claim, so local
        enqueue/requeue must be immediately discoverable. Ignore old watch
        events until they catch up with this write's revision.
        """
        if (
            self._closed
            or not callable(getattr(self._kv, "watch", None))
            or revision <= max(self._last_revision, self._local_puts.get(key, 0))
        ):
            return
        self._local_puts[key] = revision
        self._keys.setdefault(key.rpartition(".")[0] + ".", {})[key] = revision

    def discard(self, key: str, revision: int) -> None:
        """Evict a stale candidate only if a newer event has not replaced it."""
        prefix = key.rpartition(".")[0] + "."
        keys = self._keys.get(prefix)
        if keys is not None and keys.get(key) == revision:
            del keys[key]
            if not keys:
                del self._keys[prefix]

    async def _run(self) -> None:
        retry_delay = 0.5
        while not self._closed:
            watcher = None
            self._ready.clear()
            self._keys.clear()
            self._local_puts.clear()
            self._last_revision = 0
            try:
                # Replay once, then consume changes. Do not ignore deletes:
                # removing them from the index bounds memory by live work.
                watcher = await watch_kv(self._kv, ">", inactive_threshold=30)
                async for entry in watcher:
                    if entry is None:
                        self._ready.set()
                        retry_delay = 0.5
                        continue
                    self._last_revision = max(self._last_revision, entry.revision)
                    if self._local_puts.get(entry.key, 0) > entry.revision:
                        continue
                    self._local_puts.pop(entry.key, None)
                    prefix, _, _ = entry.key.rpartition(".")
                    prefix += "."
                    if entry.operation in ("DEL", "PURGE"):
                        keys = self._keys.get(prefix)
                        if keys is not None:
                            keys.pop(entry.key, None)
                            if not keys:
                                del self._keys[prefix]
                    else:
                        self._keys.setdefault(prefix, {})[entry.key] = entry.revision
                if not self._closed:
                    raise RuntimeError("NATS key watcher stopped")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Node sync key index interrupted; rebuilding after backoff", exc_info=True)
            finally:
                self._ready.clear()
                if watcher is not None:
                    with contextlib.suppress(Exception):
                        await watcher.stop()
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 30)

    async def close(self) -> None:
        self._closed = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._keys.clear()
        self._local_puts.clear()
        self._ready.set()
