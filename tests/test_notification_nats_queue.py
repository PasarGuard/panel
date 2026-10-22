import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nats import errors as nats_errors
from nats.js.errors import APIError, NotFoundError

from app.notification import nats_queue as queues


@pytest.fixture
def setup_queue(monkeypatch):
    nc = SimpleNamespace(is_closed=False, close=AsyncMock())
    consumer = SimpleNamespace(fetch=AsyncMock(return_value=[]))
    js = SimpleNamespace(
        add_stream=AsyncMock(), stream_info=AsyncMock(), pull_subscribe=AsyncMock(return_value=consumer)
    )
    connect = AsyncMock(return_value=nc)
    context = AsyncMock(return_value=js)
    monkeypatch.setattr(queues, "is_nats_enabled", lambda: True)
    monkeypatch.setattr(queues, "create_nats_client", connect)
    monkeypatch.setattr(queues, "get_jetstream_context", context)
    return SimpleNamespace(
        queue=queues.NatsNotificationQueue(), nc=nc, js=js, consumer=consumer, connect=connect, context=context
    )


@pytest.mark.asyncio
async def test_initialization_is_idempotent(setup_queue):
    state = setup_queue
    await state.queue.initialize()
    await state.queue.initialize()
    state.connect.assert_awaited_once()
    state.js.add_stream.assert_awaited_once()
    state.js.pull_subscribe.assert_awaited_once()
    state.nc.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_producer_can_upgrade_without_leaking_connection(setup_queue):
    state = setup_queue
    await state.queue.initialize(create_consumer=False)
    assert state.queue._consumer is None
    await state.queue.initialize(create_consumer=True)
    assert state.queue._consumer is state.consumer
    state.connect.assert_awaited_once()
    state.js.add_stream.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["context", "stream", "subscribe"])
async def test_failed_initialization_closes_connection_without_publishing_partial_state(setup_queue, phase):
    state = setup_queue
    failure = RuntimeError("setup failed")
    target = {"context": state.context, "stream": state.js.add_stream, "subscribe": state.js.pull_subscribe}[phase]
    target.side_effect = failure
    with pytest.raises(RuntimeError, match="setup failed"):
        await state.queue.initialize()
    state.nc.close.assert_awaited_once()
    assert (state.queue._nc, state.queue._js, state.queue._consumer) == (None, None, None)
    state.js.stream_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_stream_is_verified_after_api_error(setup_queue):
    state = setup_queue
    state.js.add_stream.side_effect = APIError(code=400)
    await state.queue.initialize()
    state.js.stream_info.assert_awaited_once_with(state.queue.STREAM_NAME)
    assert state.queue._consumer is state.consumer


@pytest.mark.asyncio
async def test_stream_creation_error_is_not_assumed_to_mean_existing_stream(setup_queue):
    state = setup_queue
    state.js.add_stream.side_effect = APIError(code=403)
    state.js.stream_info.side_effect = NotFoundError()
    with pytest.raises(NotFoundError):
        await state.queue.initialize()
    state.nc.close.assert_awaited_once()
    state.js.pull_subscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_initialization_closes_connection(setup_queue):
    state = setup_queue
    state.js.pull_subscribe.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await state.queue.initialize()
    state.nc.close.assert_awaited_once()
    assert state.queue._nc is None


@pytest.mark.asyncio
async def test_failed_upgrade_retains_working_producer(setup_queue):
    state = setup_queue
    await state.queue.initialize(create_consumer=False)
    state.js.pull_subscribe.side_effect = RuntimeError("subscribe denied")
    with pytest.raises(RuntimeError):
        await state.queue.initialize()
    assert state.queue._nc is state.nc
    assert state.queue._js is state.js
    assert state.queue._consumer is None
    state.nc.close.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("wire", [b"not-json", b"[]", b"null", b"42", b'"secret-payload"', b"\xff"])
async def test_malformed_wire_message_is_terminated_not_endlessly_retried(setup_queue, wire, caplog):
    state = setup_queue
    await state.queue.initialize()
    msg = SimpleNamespace(data=wire, ack=AsyncMock(), nak=AsyncMock(), term=AsyncMock())
    state.consumer.fetch.return_value = [msg]
    assert await state.queue.dequeue() is None
    msg.term.assert_awaited_once()
    msg.ack.assert_not_awaited()
    msg.nak.assert_not_awaited()
    assert "secret-payload" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [TimeoutError(), nats_errors.TimeoutError()])
async def test_fetch_timeout_is_empty_queue(setup_queue, failure):
    state = setup_queue
    await state.queue.initialize()
    state.consumer.fetch.side_effect = failure
    assert await state.queue.dequeue(timeout=0.1) is None


@pytest.mark.asyncio
async def test_unexpected_fetch_failure_is_not_reported_as_empty_queue(setup_queue):
    state = setup_queue
    await state.queue.initialize()
    state.consumer.fetch.side_effect = RuntimeError("broker failed")
    with pytest.raises(RuntimeError, match="broker failed"):
        await state.queue.dequeue()


@pytest.mark.asyncio
async def test_ack_failure_is_not_reported_as_empty_queue(setup_queue):
    state = setup_queue
    await state.queue.initialize()
    msg = SimpleNamespace(data=b'{"type":"webhook"}', ack=AsyncMock(side_effect=RuntimeError("ack failed")))
    state.consumer.fetch.return_value = [msg]
    with pytest.raises(RuntimeError, match="ack failed"):
        await state.queue.dequeue()


@pytest.mark.asyncio
async def test_valid_payload_preserves_legacy_dict_contract(setup_queue):
    state = setup_queue
    await state.queue.initialize()
    msg = SimpleNamespace(data=b'{"type":"webhook"}', ack=AsyncMock(), term=AsyncMock())
    state.consumer.fetch.return_value = [msg]
    assert await state.queue.dequeue() == {"type": "webhook"}
    msg.ack.assert_awaited_once()
    msg.term.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_initialization_opens_only_one_connection(setup_queue):
    state = setup_queue

    async def delayed_connect():
        await asyncio.sleep(0)
        return state.nc

    state.connect.side_effect = delayed_connect
    await asyncio.gather(state.queue.initialize(), state.queue.initialize())
    state.connect.assert_awaited_once()
    state.js.pull_subscribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_failure_releases_setup_lock_for_retry(setup_queue):
    state = setup_queue
    state.js.add_stream.side_effect = [RuntimeError("temporary failure"), None]
    with pytest.raises(RuntimeError):
        await state.queue.initialize()
    await state.queue.initialize()
    assert state.queue._nc is state.nc
    assert state.connect.await_count == 2
