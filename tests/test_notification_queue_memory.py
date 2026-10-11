"""Bounds, reservations and delays of the in-memory notification queue."""

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from app.notification import nats_queue
from app.notification.nats_queue import RETRY_METADATA_RESERVE, InMemoryNotificationQueue


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    """Controllable monotonic clock for the queue module only (asyncio keeps the real one)."""
    state = SimpleNamespace(offset=0.0)
    monkeypatch.setattr(nats_queue, "time", SimpleNamespace(monotonic=lambda: time.monotonic() + state.offset))
    return state


def _size(item: dict) -> int:
    return len(json.dumps(item).encode())


def _assert_drained(queue: InMemoryNotificationQueue):
    assert (queue._count, queue._size, queue._retry_size, queue._items) == (0, 0, 0, [])


async def test_enqueue_rejects_when_message_count_is_reached():
    queue = InMemoryNotificationQueue(maxsize=2)
    await queue.enqueue({"n": 1})
    await queue.enqueue({"n": 2})
    with pytest.raises(asyncio.QueueFull):
        await queue.enqueue({"n": 3})
    assert queue._count == 2


async def test_enqueue_rejects_when_byte_budget_is_reached():
    item = {"payload": "x" * 50}
    queue = InMemoryNotificationQueue(max_bytes=2 * _size(item))
    await queue.enqueue(item)
    await queue.enqueue(item)
    with pytest.raises(asyncio.QueueFull):
        await queue.enqueue({"n": 1})
    assert queue._size == 2 * _size(item)


async def test_reservations_hold_capacity_until_acked():
    queue = InMemoryNotificationQueue(maxsize=1)
    await queue.enqueue({"n": 1})
    delivery = await queue.dequeue(timeout=0.01)
    assert delivery is not None and delivery.data == {"n": 1}
    # The in-flight item still occupies its slot, so a retry never needs a free one.
    with pytest.raises(asyncio.QueueFull):
        await queue.enqueue({"n": 2})
    await delivery.ack()
    _assert_drained(queue)
    await queue.enqueue({"n": 2})


async def test_unsettled_delivery_is_released_back_to_the_queue():
    queue = InMemoryNotificationQueue()
    await queue.enqueue({"n": 1})
    async with await queue.dequeue(timeout=0.01) as delivery:
        assert delivery.data == {"n": 1}
    assert delivery.settled
    assert queue._count == 1
    assert await queue.dequeue(timeout=0.01) is None  # released with the default 1 s delay


async def test_delayed_item_does_not_block_ready_items(clock):
    queue = InMemoryNotificationQueue()
    await queue.enqueue({"n": 1})
    await queue.enqueue({"n": 2})
    first = await queue.dequeue(timeout=0.01)
    await first.release(delay=30)

    second = await queue.dequeue(timeout=0.01)
    assert second.data == {"n": 2}
    await second.ack()
    assert await queue.dequeue(timeout=0.01) is None

    clock.offset += 31
    again = await queue.dequeue(timeout=0.01)
    assert again.data == {"n": 1}
    await again.ack()
    _assert_drained(queue)


async def test_dequeue_wakes_up_when_an_item_is_enqueued():
    queue = InMemoryNotificationQueue()
    waiter = asyncio.create_task(queue.dequeue(timeout=5))
    await asyncio.sleep(0)
    await queue.enqueue({"n": 1})
    delivery = await asyncio.wait_for(waiter, timeout=1)
    assert delivery.data == {"n": 1}
    await delivery.ack()


async def test_retry_replaces_the_item_and_returns_retry_budget_on_ack(clock):
    queue = InMemoryNotificationQueue()
    await queue.enqueue({"n": 1, "tries": 0})
    delivery = await queue.dequeue(timeout=0.01)
    await delivery.prepare({"n": 1, "tries": 0, "pending": ["a", "b"]})
    assert queue._retry_size > 0
    await delivery.retry({"n": 1, "tries": 1, "pending": ["b"]}, delay=5)
    assert delivery.settled
    assert await queue.dequeue(timeout=0.01) is None

    clock.offset += 6
    retried = await queue.dequeue(timeout=0.01)
    assert retried.data == {"n": 1, "tries": 1, "pending": ["b"]}
    await retried.ack()
    _assert_drained(queue)


async def test_prepare_rejects_when_retry_budget_is_exhausted():
    item = {"n": 1}
    # Retry metadata has its own budget of max_bytes, and the first reservation
    # always includes RETRY_METADATA_RESERVE extra bytes.
    queue = InMemoryNotificationQueue(max_bytes=RETRY_METADATA_RESERVE - 1)
    await queue.enqueue(item)
    delivery = await queue.dequeue(timeout=0.01)
    with pytest.raises(asyncio.QueueFull):
        await delivery.prepare(item)
    assert queue._retry_size == 0
    await delivery.ack()
    _assert_drained(queue)
