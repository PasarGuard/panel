import asyncio
import hashlib
import heapq
import json
import time
from contextlib import suppress
from itertools import count
from uuid import uuid4

import nats
from nats import errors as nats_errors
from nats.js.api import AckPolicy, ConsumerConfig, DiscardPolicy, RetentionPolicy, StreamConfig
from nats.js.client import JetStreamContext
from nats.js.errors import NotFoundError

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client, get_jetstream_context
from app.utils.logger import get_logger

logger = get_logger("Notification")

PUBLISH_TIMEOUT_MAX_ATTEMPTS = 3
PUBLISH_TIMEOUT_BASE_DELAY = 0.1
QUEUE_MAX_MESSAGES = 10_000
QUEUE_MAX_BYTES = 64 * 1024 * 1024
ACK_WAIT = 60


class NotificationDelivery:
    """A reservation that is returned to the queue unless explicitly settled."""

    def __init__(self, data: dict):
        self.data = data
        self.settled = False
        self._heartbeat_task = None

    async def ack(self):
        raise NotImplementedError

    async def retry(self, item: dict, delay: float = 0):
        raise NotImplementedError

    async def release(self, delay: float = 1):
        raise NotImplementedError

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._heartbeat_task
        if not self.settled:
            await self.release()


class NotificationQueue:
    async def enqueue(self, item: dict):
        raise NotImplementedError

    async def dequeue(self, timeout: float | None = None) -> NotificationDelivery | None:
        raise NotImplementedError


class NatsNotificationDelivery(NotificationDelivery):
    def __init__(self, queue, message, data):
        super().__init__(data)
        self.queue = queue
        self.message = message

    async def __aenter__(self):
        self._heartbeat_task = asyncio.create_task(self._heartbeat())
        return self

    async def ack(self):
        await self.message.ack_sync()
        self.settled = True
        # Existing LimitsPolicy streams cannot be converted to WorkQueuePolicy.
        # Delete completed messages explicitly without recreating the durable.
        if self.queue._retention == RetentionPolicy.LIMITS:
            try:
                await self.queue._js.delete_msg(self.queue.STREAM_NAME, self.message.metadata.sequence.stream)
            except Exception:
                logger.exception("Could not remove acknowledged notification from stream")

    async def retry(self, item: dict, delay: float = 0):
        data = json.dumps(item).encode()
        # Repeating a publish after a timeout must not create another retry.
        message_id = hashlib.sha256(str(self.message.metadata.sequence.stream).encode() + b":" + data).hexdigest()
        await self.queue._publish(data, message_id)
        await self.ack()

    async def release(self, delay: float = 1):
        await self.message.nak(delay=max(delay, 0.01))
        self.settled = True

    async def _heartbeat(self):
        while True:
            await asyncio.sleep(ACK_WAIT / 3)
            if self.settled:
                return
            try:
                await self.message.in_progress()
            except Exception:
                logger.exception("Could not extend notification acknowledgement deadline")


class NatsNotificationQueue(NotificationQueue):
    def __init__(
        self,
        stream_name: str = "NOTIFICATIONS",
        subject: str = "notifications.queue",
        consumer_name: str = "notification_workers",
    ):
        self.STREAM_NAME = stream_name
        self.SUBJECT = subject
        self.CONSUMER_NAME = consumer_name
        self._nc: nats.NATS | None = None
        self._js: JetStreamContext | None = None
        self._consumer: JetStreamContext.PullSubscription | None = None
        self._retention = RetentionPolicy.WORK_QUEUE

    async def initialize(self, create_consumer: bool = True):
        if not is_nats_enabled():
            raise RuntimeError("NATS is not enabled")
        self._nc = await create_nats_client()
        if not self._nc:
            raise RuntimeError("Failed to create NATS client")
        try:
            self._js = await get_jetstream_context(self._nc)
            await self._initialize_stream(create_consumer)
        except BaseException:
            await self._nc.close()
            self._nc = self._js = self._consumer = None
            raise

    async def _initialize_stream(self, create_consumer: bool):
        try:
            info = await self._js.stream_info(self.STREAM_NAME)
        except NotFoundError:
            # add_stream is idempotent when several producers start together.
            info = await self._js.add_stream(
                StreamConfig(
                    name=self.STREAM_NAME,
                    subjects=[self.SUBJECT],
                    retention=RetentionPolicy.WORK_QUEUE,
                    discard=DiscardPolicy.NEW,
                    max_msgs=QUEUE_MAX_MESSAGES,
                    max_bytes=QUEUE_MAX_BYTES,
                )
            )

        self._retention = info.config.retention
        if info.config.subjects != [self.SUBJECT] or info.state.consumer_count > 1:
            raise RuntimeError(f"Notification stream {self.STREAM_NAME} must have a dedicated subject and consumer")
        if self._retention not in (RetentionPolicy.LIMITS, RetentionPolicy.WORK_QUEUE):
            raise RuntimeError(f"Unsupported notification retention policy: {self._retention}")
        consumer = None
        if info.state.consumer_count:
            # Never delete messages owned by a different durable consumer.
            consumer = await self._js.consumer_info(self.STREAM_NAME, self.CONSUMER_NAME)
        if self._retention == RetentionPolicy.LIMITS and consumer is not None:
            # Only the contiguous acknowledged prefix is safe to purge.
            await self._js.purge_stream(self.STREAM_NAME, seq=consumer.ack_floor.stream_seq + 1)
            info = await self._js.stream_info(self.STREAM_NAME)

        config = info.config
        # Never shrink below an existing backlog during an upgrade, and preserve
        # explicit operator limits. Reject new messages instead of evicting work.
        if config.max_msgs is None or config.max_msgs <= 0:
            config.max_msgs = max(QUEUE_MAX_MESSAGES, info.state.messages)
        if config.max_bytes is None or config.max_bytes <= 0:
            config.max_bytes = max(QUEUE_MAX_BYTES, info.state.bytes)
        config.discard = DiscardPolicy.NEW
        await self._js.update_stream(config)

        if create_consumer:
            consumer_config = (
                consumer.config
                if consumer is not None
                else ConsumerConfig(durable_name=self.CONSUMER_NAME, filter_subject=self.SUBJECT)
            )
            consumer_config.ack_policy = AckPolicy.EXPLICIT
            consumer_config.ack_wait = ACK_WAIT
            # Delayed NAKs still count as pending at the broker. They must not
            # prevent ready messages elsewhere in the bounded stream from running.
            consumer_config.max_ack_pending = config.max_msgs
            await self._js.add_consumer(self.STREAM_NAME, consumer_config)
            self._consumer = await self._js.pull_subscribe(
                subject=self.SUBJECT, durable=self.CONSUMER_NAME, stream=self.STREAM_NAME
            )

    async def _publish(self, data: bytes, message_id: str):
        if not self._js:
            raise RuntimeError("JetStream context not available")
        for attempt in range(PUBLISH_TIMEOUT_MAX_ATTEMPTS):
            try:
                await self._js.publish(self.SUBJECT, data, headers={"Nats-Msg-Id": message_id})
                return
            except TimeoutError, nats_errors.TimeoutError:
                if attempt == PUBLISH_TIMEOUT_MAX_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(PUBLISH_TIMEOUT_BASE_DELAY * (2**attempt))

    async def enqueue(self, item: dict):
        await self._publish(json.dumps(item).encode(), uuid4().hex)

    async def dequeue(self, timeout: float | None = None) -> NotificationDelivery | None:
        if not self._consumer:
            raise RuntimeError("Consumer not available")
        try:
            messages = await self._consumer.fetch(1, timeout=timeout if timeout is not None else 1)
        except TimeoutError, nats_errors.TimeoutError:
            return None
        if not messages:
            return None
        message = messages[0]
        try:
            data = json.loads(message.data)
            if not isinstance(data, dict):
                raise TypeError("Notification must be an object")
        except ValueError, TypeError:
            logger.error("Discarding malformed notification in %s", self.STREAM_NAME)
            await NatsNotificationDelivery(self, message, {}).ack()
            return None
        return NatsNotificationDelivery(self, message, data)


class InMemoryNotificationDelivery(NotificationDelivery):
    def __init__(self, queue, data, size):
        super().__init__(data)
        self.queue = queue
        self.size = size

    async def ack(self):
        self.queue._size -= self.size
        self.queue._count -= 1
        self.settled = True

    async def retry(self, item: dict, delay: float = 0):
        data = json.dumps(item).encode()
        size = len(data)
        if self.queue._size - self.size + size > self.queue.max_bytes:
            raise asyncio.QueueFull
        self.queue._size += size - self.size
        self.queue._put(json.loads(data), size, delay)
        self.settled = True

    async def release(self, delay: float = 1):
        self.queue._put(self.data, self.size, delay)
        self.settled = True


class InMemoryNotificationQueue(NotificationQueue):
    def __init__(self, maxsize: int = QUEUE_MAX_MESSAGES, max_bytes: int = QUEUE_MAX_BYTES):
        self.maxsize = maxsize
        self.max_bytes = max_bytes
        self._items = []
        self._sequence = count()
        self._changed = asyncio.Event()
        # Reservations count towards capacity, so retries never need a free slot.
        self._count = 0
        self._size = 0

    def _put(self, item: dict, size: int, delay: float):
        heapq.heappush(self._items, (time.monotonic() + max(delay, 0), next(self._sequence), item, size))
        self._changed.set()

    async def enqueue(self, item: dict):
        data = json.dumps(item).encode()
        if self._count >= self.maxsize or self._size + len(data) > self.max_bytes:
            raise asyncio.QueueFull
        self._count += 1
        self._size += len(data)
        self._put(json.loads(data), len(data), 0)

    async def dequeue(self, timeout: float | None = None) -> NotificationDelivery | None:
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            self._changed.clear()
            now = time.monotonic()
            if self._items and self._items[0][0] <= now:
                _, _, item, size = heapq.heappop(self._items)
                return InMemoryNotificationDelivery(self, item, size)
            remaining = deadline - now if deadline is not None else None
            if remaining is not None and remaining <= 0:
                return None
            if self._items:
                delay = self._items[0][0] - now
                remaining = min(remaining, delay) if remaining is not None else delay
            try:
                await asyncio.wait_for(self._changed.wait(), timeout=remaining)
            except TimeoutError:
                if deadline is not None and time.monotonic() >= deadline:
                    return None
