import asyncio
import importlib
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aiohttp import web
from pydantic import ValidationError

from app.notification.delivery import NotificationDelivery
from app.notification.queue_manager import WebhookNotification

jobs = importlib.import_module("app.jobs.send_notifications")


def item(number=1, **overrides):
    return {"payload": {"number": number}, "send_at": 0, "tries": 0, **overrides}


@pytest.fixture
def delivery(monkeypatch):
    settings = SimpleNamespace(enable=True, proxy_url=None, recurrent=3, timeout=30, webhooks=[])
    queue = SimpleNamespace(dequeue=AsyncMock(side_effect=[None]))
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=MagicMock())
    session.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=session)
    send = AsyncMock(return_value=True)
    requeue = AsyncMock()
    monkeypatch.setattr(jobs, "webhook_settings", AsyncMock(return_value=settings))
    monkeypatch.setattr(jobs, "get_webhook_queue", lambda: queue)
    monkeypatch.setattr(jobs, "create_outbound_http_session", factory)
    monkeypatch.setattr(jobs, "send_to_all_webhooks", send)

    async def claim(timeout):
        value = await queue.dequeue(timeout=timeout)
        if value is None:
            return None

        async def retry(value):
            await requeue(value["payload"], send_at=value["send_at"], tries=value["tries"])

        return NotificationDelivery(value, acknowledge=AsyncMock(), retry=retry, release=AsyncMock())

    queue.claim = claim
    return SimpleNamespace(settings=settings, queue=queue, session=session, factory=factory, send=send, requeue=requeue)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_first", [True, False])
async def test_malformed_item_does_not_crash_or_duplicate_previous_item(delivery, bad_first, caplog):
    bad = {"payload": "private malformed content"}
    entries = [bad, item()] if bad_first else [item(), bad]
    delivery.queue.dequeue.side_effect = [*entries, None]
    await jobs.send_notifications()
    assert delivery.send.await_args.args[1] == [{"number": 1}]
    delivery.requeue.assert_not_awaited()
    assert "Discarding malformed" in caplog.text
    assert "private malformed content" not in caplog.text


@pytest.mark.asyncio
async def test_disabled_webhooks_do_not_consume_queue(delivery):
    delivery.settings.enable = False
    await jobs.send_notifications()
    delivery.queue.dequeue.assert_not_awaited()
    delivery.factory.assert_not_called()


@pytest.mark.asyncio
async def test_delayed_item_is_preserved_without_sending(delivery):
    later = time.time() + 600
    delivery.queue.dequeue.side_effect = [item(send_at=later, tries=1), None]
    await jobs.send_notifications()
    delivery.send.assert_not_awaited()
    delivery.requeue.assert_awaited_once_with({"number": 1}, send_at=later, tries=1)


@pytest.mark.asyncio
async def test_delivery_failure_increments_retry_and_delays(delivery):
    delivery.queue.dequeue.side_effect = [item(), None]
    delivery.send.return_value = False
    before = time.time()
    await jobs.send_notifications()
    assert delivery.requeue.await_args.kwargs["tries"] == 1
    assert delivery.requeue.await_args.kwargs["send_at"] >= before + 30


@pytest.mark.asyncio
async def test_retry_exhaustion_does_not_requeue(delivery):
    delivery.queue.dequeue.side_effect = [item(tries=2), item(2, tries=3), None]
    delivery.send.return_value = False
    await jobs.send_notifications()
    assert delivery.send.await_args.args[1] == [{"number": 1}]
    delivery.requeue.assert_not_awaited()


@pytest.mark.asyncio
async def test_busy_queue_is_bounded_per_run(delivery):
    delivery.queue.dequeue.side_effect = None
    delivery.queue.dequeue.return_value = item()
    await jobs.send_notifications()
    assert delivery.queue.dequeue.await_count == jobs.MAX_NOTIFICATIONS_PER_RUN
    payloads = [call.args[1] for call in delivery.send.await_args_list]
    assert sum(map(len, payloads)) == jobs.MAX_NOTIFICATIONS_PER_RUN
    assert all(len(batch) <= jobs.WEBHOOK_BATCH_SIZE for batch in payloads)
    delivery.requeue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["dequeue", "send"])
async def test_unexpected_failure_restores_claimed_items(delivery, phase):
    delivery.queue.dequeue.side_effect = [item(), RuntimeError("queue down")] if phase == "dequeue" else [item(), None]
    if phase == "send":
        delivery.send.side_effect = RuntimeError("send failed")
    with pytest.raises(RuntimeError):
        await jobs.send_notifications()
    delivery.requeue.assert_awaited_once_with({"number": 1}, send_at=0, tries=0)
    delivery.session.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_task_cancellation_restores_inflight_batch(delivery):
    entered = asyncio.Event()

    async def blocked_send(*args):
        entered.set()
        await asyncio.Event().wait()

    delivery.queue.dequeue.side_effect = [item(), None]
    delivery.send.side_effect = blocked_send
    task = asyncio.create_task(jobs.send_notifications())
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        delivery.requeue.assert_awaited_once_with({"number": 1}, send_at=0, tries=0)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_later_batch_cancellation_does_not_resend_completed_batch(delivery):
    delivery.queue.dequeue.side_effect = [*(item(i) for i in range(60)), None]
    delivery.send.side_effect = [True, asyncio.CancelledError()]
    with pytest.raises(asyncio.CancelledError):
        await jobs.send_notifications()
    assert [call.args[0]["number"] for call in delivery.requeue.await_args_list] == list(range(50, 60))


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [True, False])
async def test_requeue_failure_attempts_other_items_and_preserves_cancellation(delivery, cancelled):
    delivery.queue.dequeue.side_effect = [item(1, send_at=time.time() + 600), item(2), None]
    delivery.requeue.side_effect = [RuntimeError("publish failed"), None]
    if cancelled:
        delivery.send.side_effect = asyncio.CancelledError()
        expected = asyncio.CancelledError
    else:
        delivery.send.return_value = False
        expected = ExceptionGroup
    with pytest.raises(expected):
        await jobs.send_notifications()
    assert delivery.requeue.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 201, 202, 204, 400, 500])
async def test_response_is_released_and_logs_exclude_secrets(status, caplog):
    # Use the real helper, not the processor fixture's mocked sender.
    response = SimpleNamespace(status=status)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    client = SimpleNamespace(post=MagicMock(return_value=context))
    hook = SimpleNamespace(url="https://example.test/private?token=secret-value", secret="header-secret")
    success = await jobs.send_to_all_webhooks(client, [{"event": "test"}], [hook])
    assert success is (status < 300)
    context.__aexit__.assert_awaited_once()
    assert "secret-value" not in caplog.text
    assert "header-secret" not in caplog.text


@pytest.mark.asyncio
async def test_request_exception_does_not_log_credentials(caplog):
    client = SimpleNamespace(post=MagicMock(side_effect=ValueError("https://user:secret@example.test/token")))
    assert not await jobs.send_to_all_webhooks(client, [{}], [SimpleNamespace(url="unused", secret="")])
    assert "secret" not in caplog.text
    assert "ValueError" in caplog.text


@pytest.mark.parametrize("overrides", [{"send_at": float("nan")}, {"send_at": float("inf")}, {"tries": -1}])
def test_poison_retry_metadata_is_rejected(overrides):
    with pytest.raises(ValidationError):
        WebhookNotification.model_validate(item(**overrides))


@pytest.mark.asyncio
async def test_real_http_delivery_reuses_single_connection():
    received = []

    async def handler(request):
        received.append((await request.json(), request.headers.get("x-webhook-secret")))
        return web.Response(status=204)

    app = web.Application()
    app.router.add_post("/hook", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        hook = SimpleNamespace(url=f"http://127.0.0.1:{port}/hook", secret="test-secret")
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=1), timeout=aiohttp.ClientTimeout(total=2)
        ) as client:
            for i in range(3):
                assert await jobs.send_to_all_webhooks(client, [{"number": i}], [hook])
        assert received == [([{"number": i}], "test-secret") for i in range(3)]
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_shutdown_drain_does_not_abandon_backlog_above_normal_limit(delivery):
    total = jobs.MAX_NOTIFICATIONS_PER_RUN + 7
    delivery.queue.dequeue.side_effect = [*(item(i) for i in range(total)), None]
    await jobs.send_pending_notifications_before_shutdown()
    assert sum(len(call.args[1]) for call in delivery.send.await_args_list) == total
    assert delivery.queue.dequeue.await_count == total + 1
    delivery.requeue.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_preserves_delayed_items_without_consuming_them_again(delivery):
    later = time.time() + 600
    delivery.queue.dequeue.side_effect = [item(send_at=later), None]
    await jobs.send_pending_notifications_before_shutdown()
    assert delivery.queue.dequeue.await_count == 2
    delivery.send.assert_not_awaited()
    delivery.requeue.assert_awaited_once_with({"number": 1}, send_at=later, tries=0)
