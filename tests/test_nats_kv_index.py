import asyncio
from types import SimpleNamespace

import pytest

from app.nats.kv_index import KvKeyIndex


class Watcher:
    def __init__(self, entries=()):
        self.queue = asyncio.Queue()
        for entry in entries:
            self.queue.put_nowait(entry)
        self.stopped = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        entry = await self.queue.get()
        if isinstance(entry, Exception):
            raise entry
        return entry

    async def stop(self):
        self.stopped = True


def entry(key, revision=1, operation=None):
    return SimpleNamespace(key=key, revision=revision, operation=operation)


class WatchedKv:
    def __init__(self, *watchers):
        self.watchers = iter(watchers)
        self.calls = 0

    async def watch(self, subject, **kwargs):
        assert subject == ">"
        assert kwargs["meta_only"] is True
        assert not kwargs.get("ignore_deletes")
        self.calls += 1
        return next(self.watchers)


async def eventually(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.001)


async def test_many_nodes_and_concurrent_empty_polls_share_one_watcher():
    kv = WatchedKv(Watcher([None]))
    index = KvKeyIndex(kv)
    try:
        assert await asyncio.gather(*(index.keys(f"p.{node}.") for node in range(1000))) == [[]] * 1000
        assert kv.calls == 1
        assert index._keys == {}
    finally:
        await index.close()


async def test_initial_snapshot_is_complete_before_exposing_keys():
    watcher = Watcher([entry("p.1.a"), entry("p.2.b")])
    index = KvKeyIndex(WatchedKv(watcher))
    task = asyncio.create_task(index.keys("p.1."))
    try:
        await eventually(lambda: "p.2." in index._keys)
        assert not task.done()
        watcher.queue.put_nowait(None)
        assert await task == ["p.1.a"]
        assert await index.keys("p.2.") == ["p.2.b"]
    finally:
        await index.close()


async def test_changes_remove_deleted_keys_and_empty_node_indexes():
    watcher = Watcher([entry("p.1.a"), None])
    index = KvKeyIndex(WatchedKv(watcher))
    try:
        assert await index.keys("p.1.") == ["p.1.a"]
        for number in range(1000):
            watcher.queue.put_nowait(entry(f"c.1.{number}", number + 2))
            watcher.queue.put_nowait(entry(f"c.1.{number}", number + 3, "DEL"))
        watcher.queue.put_nowait(entry("p.1.a", 3000, "PURGE"))
        await eventually(lambda: watcher.queue.empty())
        assert index._keys == {}
    finally:
        await index.close()
    assert watcher.stopped


async def test_watch_failure_rebuilds_snapshot_without_stale_keys():
    first = Watcher([entry("p.1.old"), None])
    second = Watcher([entry("p.1.new", 2), None])
    kv = WatchedKv(first, second)
    index = KvKeyIndex(kv)
    try:
        assert await index.keys("p.1.") == ["p.1.old"]
        first.queue.put_nowait(RuntimeError("connection lost"))
        await eventually(lambda: first.stopped)
        assert not index._ready.is_set()
        assert await index.keys("p.1.") == ["p.1.new"]
        assert kv.calls == 2
    finally:
        await index.close()


async def test_cancelled_caller_does_not_cancel_shared_initialization():
    watcher = Watcher()
    index = KvKeyIndex(WatchedKv(watcher))
    cancelled = asyncio.create_task(index.keys("p.1."))
    remaining = asyncio.create_task(index.keys("p.2."))
    try:
        await asyncio.sleep(0)
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        watcher.queue.put_nowait(entry("p.2.a"))
        watcher.queue.put_nowait(None)
        assert await remaining == ["p.2.a"]
    finally:
        await index.close()


async def test_close_wakes_waiters_and_rejects_future_reads():
    index = KvKeyIndex(WatchedKv(Watcher()))
    pending = asyncio.create_task(index.keys("p.1."))
    await asyncio.sleep(0)
    await index.close()
    with pytest.raises(RuntimeError, match="closed"):
        await pending
    with pytest.raises(RuntimeError, match="closed"):
        await index.keys("p.1.")


async def test_local_writes_are_visible_before_delayed_watch_events():
    watcher = Watcher([None])
    index = KvKeyIndex(WatchedKv(watcher))
    try:
        assert await index.keys("p.1.") == []
        index.observe_put("p.1.a", 3)
        index.observe_put("p.1.a", 1)  # a delayed acknowledgement cannot regress it
        watcher.queue.put_nowait(entry("p.1.a", 2, "DEL"))
        await eventually(lambda: watcher.queue.empty())
        assert await index.entries("p.1.") == {"p.1.a": 3}
        watcher.queue.put_nowait(entry("p.1.a", 3))
        await eventually(lambda: watcher.queue.empty())
        assert index._local_puts == {}
        watcher.queue.put_nowait(entry("p.1.a", 4, "DEL"))
        await eventually(lambda: watcher.queue.empty())
        index.observe_put("p.1.a", 3)  # delete already observed before publish reply
        assert await index.keys("p.1.") == []
    finally:
        await index.close()


async def test_missing_candidate_eviction_does_not_remove_a_newer_update():
    index = KvKeyIndex(WatchedKv(Watcher([entry("p.1.a", 1), None])))
    try:
        assert await index.entries("p.1.") == {"p.1.a": 1}
        index.observe_put("p.1.a", 2)
        index.discard("p.1.a", 1)
        assert await index.entries("p.1.") == {"p.1.a": 2}
        index.discard("p.1.a", 2)
        assert index._keys == {}
    finally:
        await index.close()
