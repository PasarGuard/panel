import asyncio

import pytest
from pydantic import ValidationError

from app.notification.nats_queue import InMemoryNotificationQueue, QueueOverloadedError
from config import MemoryQueueSettings, ShutdownSettings


@pytest.mark.asyncio
async def test_capacity_counts_claimed_and_queued_items():
    queue = InMemoryNotificationQueue(capacity=2, enqueue_timeout=0.01)
    await queue.enqueue({"n": 1})
    await queue.enqueue({"n": 2})
    delivery = await queue.claim()
    assert queue.inflight == 1
    with pytest.raises(QueueOverloadedError):
        await queue.enqueue({"n": 3})
    async with delivery:
        await delivery.acknowledge()
    await queue.enqueue({"n": 3})
    assert queue.q.qsize() == 2
    assert queue.inflight == 0


@pytest.mark.asyncio
async def test_reserved_retry_does_not_deadlock_with_full_capacity():
    queue = InMemoryNotificationQueue(capacity=1, enqueue_timeout=0.01)
    await queue.enqueue({"tries": 0})
    delivery = await queue.claim()
    async with delivery:
        await asyncio.wait_for(delivery.retry({"tries": 1}), timeout=0.1)
    assert await queue.dequeue(timeout=0) == {"tries": 1}
    await queue.enqueue({"tries": 2})


@pytest.mark.asyncio
async def test_cancelled_delivery_restores_reserved_item_even_after_quiesce():
    queue = InMemoryNotificationQueue(capacity=1)
    await queue.enqueue({"n": 1})
    delivery = await queue.claim()
    queue.quiesce()
    with pytest.raises(QueueOverloadedError, match="shutting down"):
        await queue.enqueue({"n": 2})
    with pytest.raises(asyncio.CancelledError):
        async with delivery:
            raise asyncio.CancelledError()
    assert queue.inflight == 0
    assert await queue.dequeue(timeout=0) == {"n": 1}


@pytest.mark.asyncio
async def test_enqueue_takes_snapshot_of_mutable_input():
    queue = InMemoryNotificationQueue(capacity=1)
    original = {"nested": {"value": "small"}}
    await queue.enqueue(original)
    original["nested"]["value"] = "changed"
    assert await queue.dequeue(timeout=0) == {"nested": {"value": "small"}}


@pytest.mark.asyncio
async def test_payload_limit_rejects_without_consuming_capacity():
    queue = InMemoryNotificationQueue(capacity=1, max_item_bytes=32)
    with pytest.raises(ValueError, match="payload limit"):
        await queue.enqueue({"data": "x" * 33})
    await queue.enqueue({"ok": True})
    assert await queue.dequeue(timeout=0) == {"ok": True}


@pytest.mark.asyncio
async def test_cancelled_waiting_producer_does_not_leak_capacity():
    queue = InMemoryNotificationQueue(capacity=1, enqueue_timeout=2)
    await queue.enqueue({"n": 1})
    producer = asyncio.create_task(queue.enqueue({"n": 2}))
    await asyncio.sleep(0)
    producer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await producer
    assert await queue.dequeue(timeout=0) == {"n": 1}
    await asyncio.wait_for(queue.enqueue({"n": 3}), timeout=0.1)


@pytest.mark.asyncio
async def test_quiesce_rejects_producer_already_waiting_for_capacity():
    queue = InMemoryNotificationQueue(capacity=1, enqueue_timeout=1)
    await queue.enqueue({"n": 1})
    producer = asyncio.create_task(queue.enqueue({"n": 2}))
    await asyncio.sleep(0)
    queue.quiesce()
    await queue.dequeue(timeout=0)
    with pytest.raises(QueueOverloadedError, match="shutting down"):
        await producer
    assert queue.q.empty()


@pytest.mark.asyncio
async def test_empty_poll_does_not_wait_forever():
    queue = InMemoryNotificationQueue(capacity=1)
    assert await asyncio.wait_for(queue.claim(timeout=0), 0.1) is None
    assert await asyncio.wait_for(queue.dequeue(timeout=0), 0.1) is None


@pytest.mark.asyncio
async def test_bad_retry_preserves_original_item_on_exit():
    queue = InMemoryNotificationQueue(capacity=1, max_item_bytes=32)
    await queue.enqueue({"n": 1})
    delivery = await queue.claim()
    with pytest.raises(ValueError):
        async with delivery:
            await delivery.retry({"data": "x" * 50})
    assert await queue.dequeue(timeout=0) == {"n": 1}


@pytest.mark.parametrize("settings", [MemoryQueueSettings, ShutdownSettings])
@pytest.mark.parametrize("invalid", [0, -1])
def test_limits_reject_nonpositive_configuration(settings, invalid):
    for field in settings.model_fields.values():
        with pytest.raises(ValidationError):
            settings(_env_file=None, **{field.validation_alias: invalid})


@pytest.mark.parametrize("field", ["SHUTDOWN_TIMEOUT", "SHUTDOWN_HOOK_TIMEOUT", "SHUTDOWN_REQUEST_DRAIN_TIMEOUT"])
@pytest.mark.parametrize("invalid", [float("nan"), float("inf")])
def test_deadlines_must_be_finite(field, invalid):
    with pytest.raises(ValidationError):
        ShutdownSettings(_env_file=None, **{field: invalid})
