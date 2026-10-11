"""Notification delivery: webhook batching and retries on both queue backends,
JetStream settlement and retry checkpoints, and Discord rate limits.

JetStream is replaced by an in-process fake and webhook/Discord endpoints by a
local aiohttp server bound to 127.0.0.1, so no NATS or outside network is needed.
"""

import asyncio
import json
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from nats import errors as nats_errors
from nats.js.api import DiscardPolicy, RawStreamMsg, RetentionPolicy, StreamConfig
from nats.js.errors import BadRequestError, NotFoundError, ServiceUnavailableError

from app.jobs import send_notifications as webhook_job
from app.models.settings import NotificationSettings, Webhook, WebhookInfo
from app.notification import client as notification_client, nats_queue, queue_manager
from app.notification.nats_queue import (
    QUEUE_MAX_BYTES,
    QUEUE_MAX_MESSAGES,
    InMemoryNotificationQueue,
    NatsNotificationQueue,
)

STREAM = "WEBHOOKS"
SUBJECT = "webhooks.queue"
RETRY_STREAM = f"{STREAM}_RETRY_STATE"
CHECKPOINT_1 = f"{SUBJECT}.retry_state.1"


# ---------------------------------------------------------------------------
# Fakes and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    """Shift the clocks used for delays and send_at without touching asyncio's clock."""
    state = SimpleNamespace(offset=0.0)
    state.monotonic = lambda: time.monotonic() + state.offset

    class ShiftedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(seconds=state.offset)

    monkeypatch.setattr(nats_queue, "time", SimpleNamespace(monotonic=state.monotonic))
    monkeypatch.setattr(webhook_job, "dt", ShiftedDatetime)
    monkeypatch.setattr(notification_client, "time", SimpleNamespace(time=lambda: time.time() + state.offset))
    return state


def _matches(pattern: str, subject: str) -> bool:
    return subject == pattern or (pattern.endswith(".*") and subject.rsplit(".", 1)[0] == pattern[:-2])


class FakeJetStream:
    """The subset of JetStreamContext used by NatsNotificationQueue, including
    expected-sequence headers, one message per subject and DiscardPolicy.NEW limits."""

    def __init__(self):
        self.streams = {}
        self.events = []

    def add(self, name, subject, *, max_msgs=QUEUE_MAX_MESSAGES, max_bytes=QUEUE_MAX_BYTES, per_subject=False):
        self.streams[name] = SimpleNamespace(
            subject=subject, msgs={}, last_seq=0, max_msgs=max_msgs, max_bytes=max_bytes, per_subject=per_subject
        )

    @staticmethod
    def _bytes(stream) -> int:
        return sum(len(msg.data) for msg in stream.msgs.values())

    @staticmethod
    def _last_for_subject(stream, subject) -> int:
        return max((seq for seq, msg in stream.msgs.items() if msg.subject == subject), default=0)

    async def publish(self, subject, payload=b"", headers=None, **_):
        name, stream = next((n, s) for n, s in self.streams.items() if _matches(s.subject, subject))
        headers = headers or {}
        if "Nats-Expected-Last-Sequence" in headers and int(headers["Nats-Expected-Last-Sequence"]) != stream.last_seq:
            raise BadRequestError(code=400, err_code=10071, description="wrong last sequence")
        expected_subject_seq = headers.get("Nats-Expected-Last-Subject-Sequence")
        if expected_subject_seq is not None and int(expected_subject_seq) != self._last_for_subject(stream, subject):
            raise BadRequestError(code=400, err_code=10071, description="wrong last sequence")
        if stream.per_subject:
            stream.msgs = {seq: msg for seq, msg in stream.msgs.items() if msg.subject != subject}
        if len(stream.msgs) >= stream.max_msgs:
            raise ServiceUnavailableError(code=503, err_code=10077, description="maximum messages exceeded")
        if self._bytes(stream) + len(payload) > stream.max_bytes:
            raise ServiceUnavailableError(code=503, err_code=10077, description="maximum bytes exceeded")
        stream.last_seq += 1
        stream.msgs[stream.last_seq] = RawStreamMsg(subject=subject, seq=stream.last_seq, data=payload)
        self.events.append(("publish", subject, payload))
        return SimpleNamespace(stream=name, seq=stream.last_seq)

    async def get_msg(self, stream_name, seq=None, subject=None, next=False, **_):
        stream = self.streams[stream_name]
        if next:
            for candidate in sorted(stream.msgs):
                if candidate >= seq and (subject is None or _matches(subject, stream.msgs[candidate].subject)):
                    return stream.msgs[candidate]
        elif seq is not None:
            if seq in stream.msgs:
                return stream.msgs[seq]
        elif last := self._last_for_subject(stream, subject):
            return stream.msgs[last]
        raise NotFoundError(code=404, err_code=10037, description="no message found")

    async def delete_msg(self, stream_name, seq):
        if self.streams[stream_name].msgs.pop(seq, None) is None:
            raise NotFoundError(code=404, err_code=10037, description="no message found")
        self.events.append(("delete", stream_name, seq))

    async def stream_info(self, name):
        stream = self.streams[name]
        return SimpleNamespace(
            config=SimpleNamespace(max_msgs=stream.max_msgs, max_bytes=stream.max_bytes),
            state=SimpleNamespace(bytes=self._bytes(stream), messages=len(stream.msgs), last_seq=stream.last_seq),
        )


class FakeMessage:
    def __init__(self, consumer, seq, data):
        self.consumer = consumer
        self.data = data
        self.metadata = SimpleNamespace(sequence=SimpleNamespace(stream=seq))
        self.acked = False
        self.naks = []

    async def ack_sync(self):
        self.acked = True
        self.consumer.settle(self, None)

    async def nak(self, delay=None):
        self.naks.append(delay)
        self.consumer.settle(self, delay)

    async def in_progress(self):
        pass


class FakeConsumer:
    """Durable pull consumer over a WorkQueue stream that honours NAK delays."""

    def __init__(self, js: FakeJetStream, clock):
        self.js = js
        self.clock = clock
        self.in_flight = set()
        self.available_at = {}
        self.messages = []

    async def fetch(self, batch=1, timeout=None):
        await asyncio.sleep(0)
        stream = self.js.streams[STREAM]
        now = self.clock.monotonic()
        for seq in sorted(stream.msgs):
            if seq not in self.in_flight and self.available_at.get(seq, 0) <= now:
                self.in_flight.add(seq)
                message = FakeMessage(self, seq, stream.msgs[seq].data)
                self.messages.append(message)
                return [message]
        raise nats_errors.TimeoutError

    def settle(self, message, delay):
        seq = message.metadata.sequence.stream
        self.in_flight.discard(seq)
        if delay is None:
            self.js.streams[STREAM].msgs.pop(seq, None)  # WorkQueue retention
            self.js.events.append(("ack", seq))
        else:
            self.available_at[seq] = self.clock.monotonic() + delay
            self.js.events.append(("nak", seq, delay))


def make_nats_queue(clock, *, max_msgs=QUEUE_MAX_MESSAGES, retry_max_bytes=QUEUE_MAX_BYTES) -> NatsNotificationQueue:
    js = FakeJetStream()
    js.add(STREAM, SUBJECT, max_msgs=max_msgs)
    js.add(RETRY_STREAM, f"{SUBJECT}.retry_state.*", max_bytes=retry_max_bytes, per_subject=True)
    queue = NatsNotificationQueue(stream_name=STREAM, subject=SUBJECT, consumer_name="workers")
    queue._js = js
    queue._consumer = FakeConsumer(js, clock)
    queue._nc = SimpleNamespace(flush=AsyncMock(), is_closed=True)
    return queue


def assert_drained(queue):
    if isinstance(queue, InMemoryNotificationQueue):
        assert (queue._count, queue._size, queue._retry_size, queue._items) == (0, 0, 0, [])
    else:
        assert queue._js.streams[STREAM].msgs == {}
        assert queue._js.streams[RETRY_STREAM].msgs == {}
        assert queue._consumer.in_flight == set()


class Receiver:
    """Records every POST per endpoint name. `script[name]` holds queued
    responses as (status, json body); `fail_always` names endpoints that return 500."""

    def __init__(self):
        self.requests = defaultdict(list)
        self.script = defaultdict(list)
        self.fail_always = set()
        self.on_request = None
        self.base_url = ""

    async def handle(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        body = await request.json()
        if self.on_request is not None:
            self.on_request(name, body)
        if self.script[name]:
            status, reply = self.script[name].pop(0)
        else:
            status, reply = (500 if name in self.fail_always else 200), None
        self.requests[name].append((status, body))
        return web.json_response(reply, status=status) if reply is not None else web.Response(status=status)

    def url(self, name: str) -> str:
        return f"{self.base_url}/{name}"

    def delivered(self, name: str) -> list:
        return [item["id"] for status, body in self.requests[name] if status == 200 for item in body]

    def batch_sizes(self, name: str) -> list[int]:
        return [len(body) for _, body in self.requests[name]]


@asynccontextmanager
async def local_receiver():
    receiver = Receiver()
    app = web.Application()
    app.router.add_post("/{name}", receiver.handle)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    receiver.base_url = str(server.make_url("")).rstrip("/")
    try:
        yield receiver
    finally:
        await server.close()


def use_webhooks(monkeypatch, receiver: Receiver, *names: str, recurrent: int = 3, timeout: int = 1) -> Webhook:
    settings = Webhook(
        enable=True,
        webhooks=[WebhookInfo(url=receiver.url(name), secret="secret") for name in names],
        timeout=timeout,
        recurrent=recurrent,
    )
    monkeypatch.setattr(webhook_job, "webhook_settings", AsyncMock(return_value=settings))
    return settings


@pytest.fixture(params=["memory", "nats"])
def webhook_queue(request, clock, monkeypatch: pytest.MonkeyPatch):
    queue = InMemoryNotificationQueue() if request.param == "memory" else make_nats_queue(clock)
    monkeypatch.setattr(queue_manager, "webhook_queue_instance", queue)
    return queue


# ---------------------------------------------------------------------------
# Webhook pipeline, on both queue backends
# ---------------------------------------------------------------------------


async def test_webhook_batches_are_capped_at_50(webhook_queue, monkeypatch):
    async with local_receiver() as receiver:
        use_webhooks(monkeypatch, receiver, "ok")
        for i in range(120):
            await queue_manager.enqueue_webhook({"id": i})
        await webhook_job.send_notifications()

    assert receiver.batch_sizes("ok") == [50, 50, 20]
    assert sorted(receiver.delivered("ok")) == list(range(120))
    assert_drained(webhook_queue)


async def test_webhook_run_stops_after_max_batches(webhook_queue, monkeypatch):
    total = webhook_job.BATCH_SIZE * webhook_job.MAX_BATCHES_PER_RUN + 1
    async with local_receiver() as receiver:
        use_webhooks(monkeypatch, receiver, "ok")
        for i in range(total):
            await queue_manager.enqueue_webhook({"id": i})
        await webhook_job.send_notifications()
        assert len(receiver.delivered("ok")) == total - 1
        await webhook_job.send_notifications()

    assert sorted(receiver.delivered("ok")) == list(range(total))
    assert_drained(webhook_queue)


async def test_partial_failure_retries_only_the_failed_destination(webhook_queue, clock, monkeypatch):
    async with local_receiver() as receiver:
        receiver.script["flaky"] = [(500, None), (500, None)]
        use_webhooks(monkeypatch, receiver, "ok", "flaky", recurrent=3, timeout=5)
        for i in range(120):
            await queue_manager.enqueue_webhook({"id": i})

        await webhook_job.send_notifications()
        # The first two batches failed at "flaky" only; the healthy endpoint got everything once.
        assert sorted(receiver.delivered("ok")) == list(range(120))
        assert sorted(receiver.delivered("flaky")) == list(range(100, 120))

        await webhook_job.send_notifications()  # retries wait for the configured timeout
        assert len(receiver.requests["flaky"]) == 3

        clock.offset += 6
        await webhook_job.send_notifications()

    assert receiver.batch_sizes("ok") == [50, 50, 20]  # no duplicates at the healthy endpoint
    assert sorted(receiver.delivered("ok")) == list(range(120))
    assert receiver.batch_sizes("flaky") == [50, 50, 20, 50, 50]
    assert sorted(receiver.delivered("flaky")) == list(range(120))
    assert_drained(webhook_queue)


async def test_exhausted_notification_is_dropped_after_recurrent_attempts(webhook_queue, clock, monkeypatch):
    async with local_receiver() as receiver:
        receiver.fail_always.add("down")
        use_webhooks(monkeypatch, receiver, "ok", "down", recurrent=3, timeout=1)
        await queue_manager.enqueue_webhook({"id": 7})
        for _ in range(5):
            await webhook_job.send_notifications()
            clock.offset += 2

    assert receiver.delivered("ok") == [7]
    assert receiver.requests["down"] == [(500, [{"id": 7}])] * 3
    assert_drained(webhook_queue)


async def test_future_send_at_is_held_without_blocking_ready_notifications(webhook_queue, clock, monkeypatch):
    async with local_receiver() as receiver:
        use_webhooks(monkeypatch, receiver, "ok")
        await queue_manager.enqueue_webhook({"id": "later"}, send_at=time.time() + 30)
        await queue_manager.enqueue_webhook({"id": "now"})

        await webhook_job.send_notifications()
        assert receiver.delivered("ok") == ["now"]

        clock.offset += 31
        await webhook_job.send_notifications()

    assert receiver.delivered("ok") == ["now", "later"]
    assert_drained(webhook_queue)


async def test_removed_destination_is_not_retried(webhook_queue, clock, monkeypatch):
    async with local_receiver() as receiver:
        receiver.fail_always.add("old")
        use_webhooks(monkeypatch, receiver, "ok", "old", recurrent=3, timeout=1)
        await queue_manager.enqueue_webhook({"id": 1})
        await webhook_job.send_notifications()
        assert len(receiver.requests["old"]) == 1

        use_webhooks(monkeypatch, receiver, "ok", recurrent=3, timeout=1)
        clock.offset += 2
        await webhook_job.send_notifications()

    assert receiver.delivered("ok") == [1]
    assert len(receiver.requests["old"]) == 1
    assert_drained(webhook_queue)


# ---------------------------------------------------------------------------
# JetStream settlement and retry checkpoints
# ---------------------------------------------------------------------------


async def test_nats_message_is_acked_only_after_the_webhook_accepted_it(clock, monkeypatch):
    queue = make_nats_queue(clock)
    monkeypatch.setattr(queue_manager, "webhook_queue_instance", queue)
    events_during_request = []
    async with local_receiver() as receiver:
        receiver.on_request = lambda name, body: events_during_request.append(list(queue._js.events))
        use_webhooks(monkeypatch, receiver, "ok")
        await queue_manager.enqueue_webhook({"id": 1})
        await webhook_job.send_notifications()

    assert receiver.delivered("ok") == [1]
    assert ("ack", 1) not in events_during_request[0]
    assert ("ack", 1) in queue._js.events
    assert_drained(queue)


async def test_nats_failed_webhook_keeps_the_message_and_checkpoints_failed_destinations(clock, monkeypatch):
    queue = make_nats_queue(clock)
    monkeypatch.setattr(queue_manager, "webhook_queue_instance", queue)
    async with local_receiver() as receiver:
        receiver.fail_always.add("down")
        settings = use_webhooks(monkeypatch, receiver, "ok", "down", recurrent=3, timeout=4)
        await queue_manager.enqueue_webhook({"id": 1})
        await webhook_job.send_notifications()

    message = queue._consumer.messages[0]
    assert not message.acked
    assert message.naks == [settings.timeout]
    assert 1 in queue._js.streams[STREAM].msgs
    [checkpoint] = queue._js.streams[RETRY_STREAM].msgs.values()
    assert checkpoint.subject == CHECKPOINT_1
    state = json.loads(checkpoint.data)
    assert state["completed"] is False
    assert state["data"]["tries"] == 1
    assert state["data"]["pending_webhooks"] == [receiver.url("down")]


async def test_nats_unsettled_delivery_is_released_not_acked(clock):
    queue = make_nats_queue(clock)
    await queue.enqueue({"id": 1})
    async with await queue.dequeue(timeout=0.01) as delivery:
        assert delivery.data == {"id": 1}

    assert delivery.message.naks == [1]
    assert not delivery.message.acked
    assert 1 in queue._js.streams[STREAM].msgs


async def test_nats_retry_checkpoint_is_written_and_read_back_on_redelivery(clock):
    queue = make_nats_queue(clock)
    await queue.enqueue({"id": 1, "tries": 0})
    delivery = await queue.dequeue(timeout=0.01)
    async with delivery:
        await delivery.prepare({"id": 1, "tries": 0, "pending": ["a", "b"]})
        await delivery.retry({"id": 1, "tries": 1, "pending": ["b"]}, delay=5)

    assert delivery.message.naks == [5]
    assert not delivery.message.acked
    checkpoints = list(queue._js.streams[RETRY_STREAM].msgs.values())
    assert [checkpoint.subject for checkpoint in checkpoints] == [CHECKPOINT_1]
    assert json.loads(checkpoints[0].data) == {"data": {"id": 1, "tries": 1, "pending": ["b"]}, "completed": False}
    # Records are fixed size, so a retry never needs more journal capacity.
    sizes = {len(event[2]) for event in queue._js.events if event[:2] == ("publish", CHECKPOINT_1)}
    assert len(sizes) == 1

    assert await queue.dequeue(timeout=0.01) is None  # NAK delay not elapsed
    clock.offset += 6
    redelivered = await queue.dequeue(timeout=0.01)
    assert redelivered.data == {"id": 1, "tries": 1, "pending": ["b"]}
    async with redelivered:
        await redelivered.ack()

    assert redelivered.message.acked
    events = queue._js.events
    before_ack = events[events.index(("ack", 1)) - 1]
    assert before_ack[:2] == ("publish", CHECKPOINT_1)
    assert json.loads(before_ack[2])["completed"] is True  # completion recorded before the ack
    assert_drained(queue)


async def test_nats_completed_checkpoint_is_acked_without_redelivery(clock):
    """A crash between recording completion and acking must not resend the notification."""
    queue = make_nats_queue(clock)
    await queue.enqueue({"id": 1})
    await queue._js.publish(CHECKPOINT_1, json.dumps({"data": {"id": 1}, "completed": True}).encode())

    assert await queue.dequeue(timeout=0.01) is None
    assert queue._consumer.messages[0].acked
    assert_drained(queue)


async def test_nats_prepare_without_retry_headroom_defers_the_webhook(clock, monkeypatch):
    queue = make_nats_queue(clock, retry_max_bytes=2048)
    monkeypatch.setattr(queue_manager, "webhook_queue_instance", queue)
    async with local_receiver() as receiver:
        settings = use_webhooks(monkeypatch, receiver, "ok", timeout=3)
        await queue_manager.enqueue_webhook({"id": 1})
        await webhook_job.send_notifications()

    assert receiver.requests == {}
    message = queue._consumer.messages[0]
    assert message.naks == [settings.timeout]
    assert not message.acked
    assert queue._js.streams[RETRY_STREAM].msgs == {}


async def test_nats_malformed_message_is_discarded(clock):
    queue = make_nats_queue(clock)
    await queue._js.publish(SUBJECT, b"not json")
    assert await queue.dequeue(timeout=0.01) is None
    assert queue._consumer.messages[0].acked
    assert_drained(queue)


# ---------------------------------------------------------------------------
# Stricter JetStream startup checks
# ---------------------------------------------------------------------------


def _stream_info(config: StreamConfig, *, consumer_count=0, messages=0, bytes_=0):
    return SimpleNamespace(
        config=config, state=SimpleNamespace(consumer_count=consumer_count, messages=messages, bytes=bytes_, last_seq=0)
    )


def _startup_js(infos: dict):
    async def stream_info(name):
        if name not in infos:
            raise NotFoundError(code=404, err_code=10059, description="stream not found")
        return infos[name]

    async def add_stream(config):
        infos[config.name] = _stream_info(config)
        return infos[config.name]

    return SimpleNamespace(
        stream_info=AsyncMock(side_effect=stream_info),
        add_stream=AsyncMock(side_effect=add_stream),
        update_stream=AsyncMock(),
        get_msg=AsyncMock(side_effect=NotFoundError(code=404, err_code=10037, description="no message found")),
        add_consumer=AsyncMock(),
        pull_subscribe=AsyncMock(return_value="consumer"),
    )


def _queue_with(js) -> NatsNotificationQueue:
    queue = NatsNotificationQueue(stream_name=STREAM, subject=SUBJECT, consumer_name="workers")
    queue._js = js
    return queue


async def test_startup_creates_bounded_work_queue_streams():
    js = _startup_js({})
    queue = _queue_with(js)
    await queue._initialize_stream(create_consumer=True)

    main, retry = (call.args[0] for call in js.add_stream.await_args_list)
    assert (main.retention, main.discard) == (RetentionPolicy.WORK_QUEUE, DiscardPolicy.NEW)
    assert (main.max_msgs, main.max_bytes) == (QUEUE_MAX_MESSAGES, QUEUE_MAX_BYTES)
    assert retry.name == RETRY_STREAM
    assert retry.subjects == [f"{SUBJECT}.retry_state.*"]
    assert retry.max_msgs_per_subject == 1
    js.update_stream.assert_awaited_once()
    assert queue._consumer == "consumer"


async def test_producer_startup_updates_stream_but_skips_retry_state_and_consumer():
    js = _startup_js({})
    await _queue_with(js)._initialize_stream(create_consumer=False)

    assert [call.args[0].name for call in js.add_stream.await_args_list] == [STREAM]
    js.update_stream.assert_awaited_once()
    js.add_consumer.assert_not_awaited()


@pytest.mark.parametrize(
    ("subjects", "consumer_count"),
    [([SUBJECT, "other.subject"], 0), ([SUBJECT], 2)],
    ids=["shared-subjects", "second-consumer"],
)
async def test_startup_rejects_shared_notification_stream(subjects, consumer_count):
    config = StreamConfig(name=STREAM, subjects=subjects, retention=RetentionPolicy.WORK_QUEUE)
    js = _startup_js({STREAM: _stream_info(config, consumer_count=consumer_count)})
    with pytest.raises(RuntimeError, match="dedicated subject and consumer"):
        await _queue_with(js)._initialize_stream(create_consumer=False)
    js.update_stream.assert_not_awaited()


async def test_startup_rejects_incompatible_retry_stream():
    main = StreamConfig(name=STREAM, subjects=[SUBJECT], retention=RetentionPolicy.WORK_QUEUE)
    retry = StreamConfig(name=RETRY_STREAM, subjects=["somewhere.else.*"], retention=RetentionPolicy.LIMITS)
    js = _startup_js({STREAM: _stream_info(main), RETRY_STREAM: _stream_info(retry)})
    with pytest.raises(RuntimeError, match="Incompatible notification retry stream"):
        await _queue_with(js)._initialize_stream(create_consumer=True)
    js.add_consumer.assert_not_awaited()


async def test_startup_fails_without_retry_headroom():
    main = StreamConfig(name=STREAM, subjects=[SUBJECT], retention=RetentionPolicy.WORK_QUEUE)
    retry = StreamConfig(
        name=RETRY_STREAM,
        subjects=[f"{SUBJECT}.retry_state.*"],
        retention=RetentionPolicy.LIMITS,
        discard=DiscardPolicy.NEW,
        max_msgs=100,
        max_bytes=1000,
        max_msgs_per_subject=1,
    )
    js = _startup_js({STREAM: _stream_info(main), RETRY_STREAM: _stream_info(retry, messages=3, bytes_=600)})
    with pytest.raises(RuntimeError, match="Insufficient notification retry headroom"):
        await _queue_with(js)._initialize_stream(create_consumer=True)
    js.add_consumer.assert_not_awaited()


# ---------------------------------------------------------------------------
# Discord / Telegram dispatcher
# ---------------------------------------------------------------------------


@asynccontextmanager
async def discord_setup(monkeypatch, max_retries: int):
    queue = InMemoryNotificationQueue()
    monkeypatch.setattr(queue_manager, "queue_instance", queue)
    # The settings validator requires a real Discord URL; the queued item carries the local one.
    settings = NotificationSettings.model_construct(notify_discord=True, max_retries=max_retries)
    monkeypatch.setattr(notification_client, "notification_settings", AsyncMock(return_value=settings))
    async with local_receiver() as receiver, aiohttp.ClientSession() as session:
        monkeypatch.setattr(notification_client, "client", session)
        yield queue, receiver


async def _process_one(queue) -> bool:
    delivery = await queue.dequeue(timeout=0.01)
    if delivery is None:
        return False
    await notification_client.process_notification(delivery)
    return True


async def test_discord_rate_limit_becomes_a_queue_delay(clock, monkeypatch):
    async with discord_setup(monkeypatch, max_retries=3) as (queue, receiver):
        receiver.script["discord"] = [(429, {"retry_after": 30})]
        await queue_manager.enqueue_discord({"content": "hello"}, receiver.url("discord"))

        assert await _process_one(queue)
        assert not await _process_one(queue)  # waiting for retry_after, the worker is free

        clock.offset += 31
        retried = await queue.dequeue(timeout=0.01)
        assert retried.data["tries"] == 1
        await notification_client.process_notification(retried)

    assert [status for status, _ in receiver.requests["discord"]] == [429, 200]
    assert_drained(queue)


async def test_discord_notification_is_dropped_after_max_retries(clock, monkeypatch):
    async with discord_setup(monkeypatch, max_retries=2) as (queue, receiver):
        receiver.fail_always.add("discord")
        await queue_manager.enqueue_discord({"content": "hello"}, receiver.url("discord"))
        for _ in range(4):
            await _process_one(queue)
            clock.offset += 2

    assert [status for status, _ in receiver.requests["discord"]] == [500, 500]
    assert_drained(queue)
