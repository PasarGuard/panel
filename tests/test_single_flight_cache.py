import asyncio

import pytest

from app.utils.single_flight_cache import SingleFlightCache


async def test_failed_refresh_drops_old_value_and_next_read_retries():
    values = iter(["old", RuntimeError("db down"), "new"])

    async def loader():
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return value

    cache = SingleFlightCache(loader)
    assert await cache() == "old"

    await cache.refresh()  # logs, does not raise into PUT /api/settings or the NATS handler

    assert await cache() == "new"


async def test_failed_load_is_shared_then_retried():
    calls = 0
    gate = asyncio.Event()

    async def loader():
        nonlocal calls
        calls += 1
        await gate.wait()
        raise RuntimeError("pool timeout")

    cache = SingleFlightCache(loader)
    readers = [asyncio.create_task(cache()) for _ in range(5)]
    await asyncio.sleep(0)
    gate.set()
    results = await asyncio.gather(*readers, return_exceptions=True)

    assert calls == 1
    assert all(isinstance(result, RuntimeError) for result in results)
    with pytest.raises(RuntimeError):
        await cache()
    assert calls == 2


async def test_cancelled_reader_does_not_cancel_shared_load():
    gate = asyncio.Event()

    async def loader():
        await gate.wait()
        return "value"

    cache = SingleFlightCache(loader)
    first = asyncio.create_task(cache())
    second = asyncio.create_task(cache())
    await asyncio.sleep(0)
    first.cancel()
    gate.set()

    assert await second == "value"
    assert await cache() == "value"


async def test_overlapping_refresh_returns_after_latest_value_is_stored():
    db = {"value": "old"}
    gates = []

    async def loader():
        snapshot = db["value"]
        gate = asyncio.Event()
        gates.append(gate)
        await gate.wait()
        return snapshot

    async def loads_started(n):
        async with asyncio.timeout(1):
            while len(gates) < n:
                await asyncio.sleep(0)

    cache = SingleFlightCache(loader)
    first_load = asyncio.create_task(cache())
    await loads_started(1)
    gates[0].set()
    assert await first_load == "old"

    db["value"] = "saved"
    local = asyncio.create_task(cache.refresh())  # PUT /api/settings on this worker
    await loads_started(2)
    nats = asyncio.create_task(cache.refresh())  # the NATS message for the same save
    await loads_started(3)
    gates[1].set()
    for _ in range(5):
        await asyncio.sleep(0)
    assert not local.done()  # its own load finished, but a newer one is still running

    gates[2].set()
    await asyncio.gather(local, nats)
    assert await cache() == "saved"
