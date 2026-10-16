import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import OperationalError

from app.core import manager as manager_module
from app.core.manager import CoreManager
from app.db.models import CoreType

pytestmark = pytest.mark.asyncio


def row(core_id=1, tag="old", port=10001):
    return SimpleNamespace(
        id=core_id,
        name=tag,
        type=CoreType.xray,
        config={
            "inbounds": [
                {"tag": tag, "port": port, "protocol": "vless", "settings": {"decryption": "none", "clients": []}}
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        },
        exclude_inbound_tags=set(),
        fallbacks_inbound_tags=set(),
    )


class Reads:
    def __init__(self):
        self.slots = {}

    def add(self, name, rows=(), *, error=None, blocked=False):
        slot = SimpleNamespace(rows=deepcopy(list(rows)), error=error, started=asyncio.Event(), release=asyncio.Event())
        if not blocked:
            slot.release.set()
        self.slots[name] = slot
        return slot

    async def query(self, db, query):
        slot = self.slots[db]
        slot.started.set()
        await slot.release.wait()
        if slot.error is not None:
            raise slot.error
        return slot.rows, len(slot.rows)


@pytest.fixture
def reads(monkeypatch):
    result = Reads()
    monkeypatch.setattr(manager_module, "get_core_configs", result.query)
    return result


@pytest.fixture
def manager():
    result = CoreManager()
    result._persist_state = AsyncMock()
    return result


@asynccontextmanager
async def slow_refresh(manager, reads, rows, core_ids):
    slot = reads.add("slow", rows, blocked=True)
    task = asyncio.create_task(manager.get_cores(core_ids, db="slow"))
    try:
        await asyncio.wait_for(slot.started.wait(), 2)
        yield task, slot.release
    finally:
        slot.release.set()
        await asyncio.gather(task, return_exceptions=True)


async def assert_state(manager, expected):
    cores = await manager.get_cores()
    assert {key: core.inbounds[0] for key, core in cores.items()} == expected
    assert set(await manager.get_inbounds()) == set(expected.values())
    assert set(await manager.get_inbounds_by_tag()) == set(expected.values())


@pytest.mark.parametrize("scope", [None, {1}])
async def test_slow_refresh_does_not_block_readers_or_local_edits(manager, reads, scope):
    await manager._update_core_local(row())
    async with slow_refresh(manager, reads, [row()], scope) as (task, release):
        async with asyncio.timeout(2):
            await assert_state(manager, {1: "old"})
            assert (await manager.get_core(1)).inbounds == ["old"]
            assert (await manager.get_inbound_by_tag("old"))["tag"] == "old"
            await manager._update_core_local(row(tag="edited"))
        release.set()
        result = await task
    assert result[1].inbounds == ["edited"]
    await assert_state(manager, {1: "edited"})


@pytest.mark.parametrize("older_scope", [None, {1, 2}])
@pytest.mark.parametrize("newer_scope", [None, {1}])
async def test_overlapping_refreshes_complete_out_of_order(manager, reads, older_scope, newer_scope):
    await manager._update_core_local(row())
    async with slow_refresh(manager, reads, [row(), row(2, "second")], older_scope) as (task, release):
        reads.add("new", [row(tag="new")])
        await manager.get_cores(newer_scope, db="new")
        release.set()
        result = await task
    expected = {1: "new", 2: "second"} if newer_scope is not None else {1: "new"}
    assert {key: core.inbounds[0] for key, core in result.items()} == expected
    await assert_state(manager, expected)


async def test_disjoint_scoped_refreshes_both_survive(manager, reads):
    async with slow_refresh(manager, reads, [row()], {1}) as (task, release):
        reads.add("new", [row(2, "second")])
        await manager.get_cores({2}, db="new")
        release.set()
        assert set(await task) == {1}
    await assert_state(manager, {1: "old", 2: "second"})


@pytest.mark.parametrize("scope", [None, {1}])
@pytest.mark.parametrize("initially_present", [False, True])
async def test_local_delete_fences_refresh_even_when_core_was_absent(manager, reads, scope, initially_present):
    if initially_present:
        await manager._update_core_local(row())
    async with slow_refresh(manager, reads, [row()], scope) as (task, release):
        await asyncio.wait_for(manager._remove_core_local(1), 2)
        release.set()
        assert await task == {}
    await assert_state(manager, {})


@pytest.mark.parametrize("older_scope", [None, {7}])
async def test_newer_full_refresh_fences_unknown_absent_ids(manager, reads, older_scope):
    async with slow_refresh(manager, reads, [row(7, "deleted")], older_scope) as (task, release):
        reads.add("new", [])
        await manager.get_cores(db="new")
        release.set()
        assert await task == {}
    await assert_state(manager, {})


async def test_old_full_refresh_keeps_newer_scoped_deletion(manager, reads):
    await manager._update_core_local(row())
    async with slow_refresh(manager, reads, [row(), row(2, "second")], None) as (task, release):
        reads.add("new", [])
        await manager.get_cores({1}, db="new")
        release.set()
        assert set(await task) == {2}
    await assert_state(manager, {2: "second"})


async def test_failed_newer_read_does_not_fence_successful_older_refresh(manager, reads):
    await manager._update_core_local(row())
    async with slow_refresh(manager, reads, [row(tag="refreshed")], None) as (task, release):
        reads.add("new", error=OperationalError("select", {}, RuntimeError("offline")))
        with pytest.raises(OperationalError):
            await manager.get_cores(db="new")
        await assert_state(manager, {1: "old"})
        release.set()
        await task
    await assert_state(manager, {1: "refreshed"})
    reads.add("recovered", [row(tag="recovered")])
    await manager.get_cores(db="recovered")
    await assert_state(manager, {1: "recovered"})


async def test_cancelled_refresh_leaves_cache_readable_and_unchanged(manager, reads):
    await manager._update_core_local(row())
    async with slow_refresh(manager, reads, [row(tag="uncommitted")], None) as (task, _):
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(assert_state(manager, {1: "old"}), 2)


async def test_invalid_old_result_does_not_evict_newer_valid_core(manager, reads):
    invalid = row()
    invalid.config = {}
    async with slow_refresh(manager, reads, [invalid], {1}) as (task, release):
        await manager._update_core_local(row(tag="valid"))
        release.set()
        result = await task
    assert result[1].inbounds == ["valid"]
    await assert_state(manager, {1: "valid"})


async def test_full_refresh_preserves_unrelated_new_local_core(manager, reads):
    async with slow_refresh(manager, reads, [], None) as (task, release):
        await manager._update_core_local(row(2, "new-local"))
        release.set()
        assert set(await task) == {2}
    await assert_state(manager, {2: "new-local"})


@pytest.mark.parametrize("scope", [None, {1, 2}])
async def test_index_failure_cannot_partially_replace_cache(manager, reads, monkeypatch, scope):
    await manager._update_core_local(row())
    good = manager.validate_core(row(2, "second").config, type=CoreType.xray)

    class BrokenIndex:
        @property
        def inbounds_by_tag(self):
            raise RuntimeError("index failed")

    reads.add("bad-index", [row(), row(2, "second")])
    monkeypatch.setattr(
        manager, "validate_core", lambda config, *args: BrokenIndex() if config == row().config else good
    )
    with pytest.raises(RuntimeError, match="index failed"):
        await manager.get_cores(scope, db="bad-index")
    await assert_state(manager, {1: "old"})


@pytest.mark.parametrize("scope", [None, {1}])
async def test_failed_scoped_or_full_read_leaves_all_committed_indexes_unchanged(manager, reads, scope):
    await manager._update_core_local(row())
    await manager._update_core_local(row(2, "second"))
    reads.add("failed", error=OperationalError("select", {}, RuntimeError("offline")))
    with pytest.raises(OperationalError):
        await manager.get_cores(scope, db="failed")
    await assert_state(manager, {1: "old", 2: "second"})
