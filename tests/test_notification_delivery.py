import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.notification import client
from app.notification.delivery import NotificationDelivery
from app.notification.nats_queue import InMemoryNotificationQueue, NatsNotificationQueue


def receipt(item=None):
    return NotificationDelivery(
        item or {"type": "telegram", "message": "hello"},
        acknowledge=AsyncMock(),
        retry=AsyncMock(),
        release=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_claim_does_not_ack_before_processing(monkeypatch):
    delivery = receipt()

    async def process(item):
        delivery._acknowledge.assert_not_awaited()
        return True

    monkeypatch.setattr(client, "process_notification", process)
    await client.consume_notification(SimpleNamespace(claim=AsyncMock(return_value=delivery)))
    delivery._acknowledge.assert_awaited_once()
    delivery._release.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_consumer_releases_unacknowledged_delivery(monkeypatch):
    delivery = receipt()
    monkeypatch.setattr(client, "process_notification", AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await client.consume_notification(SimpleNamespace(claim=AsyncMock(return_value=delivery)))
    delivery._acknowledge.assert_not_awaited()
    delivery._release.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_delivery_retries_with_bounded_attempts(monkeypatch):
    monkeypatch.setattr(client, "process_notification", AsyncMock(return_value=False))
    for tries in (0, 1, 2):
        delivery = receipt({"type": "telegram", "message": "hello", "tries": tries})
        await client.consume_notification(SimpleNamespace(claim=AsyncMock(return_value=delivery)))
        if tries < 2:
            assert delivery._retry.await_args.args[0]["tries"] == tries + 1
            delivery._acknowledge.assert_not_awaited()
        else:
            delivery._acknowledge.assert_awaited_once()
            delivery._retry.assert_not_awaited()


@pytest.mark.asyncio
async def test_memory_claim_restores_item_on_cancellation():
    queue = InMemoryNotificationQueue()
    await queue.enqueue({"message": "hello"})
    delivery = await queue.claim()
    with pytest.raises(asyncio.CancelledError):
        async with delivery:
            raise asyncio.CancelledError()
    assert await queue.dequeue(timeout=0.1) == {"message": "hello"}


@pytest.mark.asyncio
async def test_nats_retry_persists_before_acknowledging_original():
    queue = NatsNotificationQueue()
    msg = SimpleNamespace(ack_sync=AsyncMock(), nak=AsyncMock(), in_progress=AsyncMock())
    queue._fetch = AsyncMock(return_value=(msg, {"tries": 0}))

    async def publish(item):
        msg.ack_sync.assert_not_awaited()

    queue.enqueue = AsyncMock(side_effect=publish)
    delivery = await queue.claim()
    async with delivery:
        msg.ack_sync.assert_not_awaited()
        await delivery.retry({"tries": 1})
    msg.ack_sync.assert_awaited_once()
    msg.nak.assert_not_awaited()
    assert delivery._heartbeat_task.done()


@pytest.mark.asyncio
async def test_failed_publish_does_not_ack_original():
    queue = NatsNotificationQueue()
    msg = SimpleNamespace(ack_sync=AsyncMock(), nak=AsyncMock(), in_progress=AsyncMock())
    queue._fetch = AsyncMock(return_value=(msg, {"tries": 0}))
    queue.enqueue = AsyncMock(side_effect=RuntimeError("broker down"))
    delivery = await queue.claim()
    with pytest.raises(RuntimeError):
        async with delivery:
            await delivery.retry({"tries": 1})
    msg.ack_sync.assert_not_awaited()
    msg.nak.assert_awaited_once_with(delay=1)


@pytest.mark.asyncio
async def test_lease_heartbeat_is_cancelled_on_exit(monkeypatch):
    import app.notification.delivery as module

    tick = asyncio.Event()
    release = asyncio.Event()
    actual_sleep = asyncio.sleep

    async def fast_sleep(delay):
        if delay == 10:
            await release.wait()
        else:
            await actual_sleep(delay)

    monkeypatch.setattr(module.asyncio, "sleep", fast_sleep)
    delivery = receipt()

    async def heartbeat():
        tick.set()
        release.clear()

    delivery._heartbeat = heartbeat
    async with delivery:
        release.set()
        await asyncio.wait_for(tick.wait(), 1)
        await delivery.acknowledge()
    assert delivery._heartbeat_task.done()
