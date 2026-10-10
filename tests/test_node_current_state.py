"""Current-state reads at delivery time: coalescing, freshness, failure isolation, and removal semantics."""

import asyncio
import contextlib

import pytest
from PasarGuardNodeBridge.common.service_pb2 import User

from app.node import sync as node_sync


class FakeDB:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def proto(user_id, inbounds=("in",)):
    return User(email=str(user_id), inbounds=list(inbounds))


@pytest.fixture
def reader(monkeypatch):
    monkeypatch.setattr(node_sync, "GetDB", FakeDB)
    calls = []

    async def core_users(db, inbound_tags=None, allowed_protocols=None, user_ids=None):
        calls.append(sorted(user_ids))
        return [proto(user_id) for user_id in user_ids if user_id % 2 == 1]  # odd ids exist and are active

    monkeypatch.setattr(node_sync, "core_users", core_users)
    instance = node_sync.CurrentStateReader(gather_seconds=0.01, max_ids_per_query=400, query_timeout=0.5)
    monkeypatch.setattr(node_sync, "_current_state", instance)
    return instance, calls


@pytest.mark.asyncio
async def test_concurrent_requests_share_one_indexed_query(reader):
    instance, calls = reader
    first, second = await asyncio.gather(instance.get([1, 2]), instance.get([3]))
    assert calls == [[1, 2, 3]]
    assert first == {1: first[1], 2: None} and first[1].email == "1"
    assert second[3].email == "3"


@pytest.mark.asyncio
async def test_request_registered_after_a_query_started_is_served_by_the_next_query(monkeypatch, reader):
    instance, calls = reader
    started, release = asyncio.Event(), asyncio.Event()
    original = node_sync.core_users

    async def blocking_core_users(db, **kwargs):
        started.set()
        await release.wait()
        return await original(db, **kwargs)

    monkeypatch.setattr(node_sync, "core_users", blocking_core_users)
    first = asyncio.create_task(instance.get([1]))
    await started.wait()
    # Registered while the first query is in flight: must not be answered by that read.
    second = asyncio.create_task(instance.get([3]))
    await asyncio.sleep(0.05)
    assert not second.done()
    release.set()
    assert (await first)[1].email == "1"
    assert (await second)[3].email == "3"  # no third request was needed to wake it
    assert calls == [[1], [3]]


@pytest.mark.asyncio
async def test_hung_query_fails_only_its_batch_and_later_requests_recover(monkeypatch, reader):
    instance, _ = reader
    original = node_sync.core_users
    hang = True

    async def maybe_hanging(db, **kwargs):
        if hang:
            await asyncio.sleep(10)
        return await original(db, **kwargs)

    monkeypatch.setattr(node_sync, "core_users", maybe_hanging)
    with pytest.raises(TimeoutError):
        await instance.get([1])
    hang = False
    assert (await instance.get([3]))[3].email == "3"
    assert not instance._pending


@pytest.mark.asyncio
async def test_cancelling_one_waiter_does_not_affect_its_sibling(monkeypatch, reader):
    instance, calls = reader
    started, release = asyncio.Event(), asyncio.Event()
    original = node_sync.core_users

    async def blocking_core_users(db, **kwargs):
        started.set()
        await release.wait()
        return await original(db, **kwargs)

    monkeypatch.setattr(node_sync, "core_users", blocking_core_users)
    first = asyncio.create_task(instance.get([1]))
    second = asyncio.create_task(instance.get([3]))
    await started.wait()
    first.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await first
    release.set()
    assert (await second)[3].email == "3"
    assert calls == [[1, 3]]


@pytest.mark.asyncio
async def test_large_batches_are_split_into_bounded_queries(reader):
    instance, calls = reader
    ids = list(range(1, 901))
    result = await instance.get(ids)
    assert len(calls) == 3 and all(len(call) <= 400 for call in calls)
    assert sum(1 for value in result.values() if value is not None) == 450


@pytest.mark.asyncio
async def test_refresh_resolves_missing_disabled_and_blocked_users_to_removals(reader):
    del reader  # fixture installs the fake reader
    # Even ids are not returned by the query (deleted, disabled/expired, no inbounds, or admin-blocked).
    payloads = {user.email: user for user in await node_sync.refresh_node_users("9", ["1", "2", "not-a-user", "4"])}
    assert list(payloads["1"].inbounds) == ["in"]
    assert list(payloads["2"].inbounds) == [] and list(payloads["4"].inbounds) == []
    assert "not-a-user" not in payloads  # callers keep their queued payload for non-panel identities


@pytest.mark.asyncio
async def test_twelve_nodes_delivering_the_same_user_share_reads(reader):
    _, calls = reader
    results = await asyncio.gather(*(node_sync.refresh_node_users(str(node), ["1"]) for node in range(12)))
    assert all(list(result[0].inbounds) == ["in"] for result in results)
    assert len(calls) <= 2


@pytest.mark.asyncio
async def test_empty_and_non_numeric_requests_do_not_query(reader):
    instance, calls = reader
    assert await node_sync.refresh_node_users("9", ["not-a-user"]) == []
    assert await instance.get([]) == {}
    assert calls == []
