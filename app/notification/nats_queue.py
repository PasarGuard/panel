import asyncio
import json
import math

import nats
from nats import errors as nats_errors
from nats.js.client import JetStreamContext

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client, get_jetstream_context
from app.notification.delivery import NotificationDelivery
from app.utils.logger import get_logger
from config import memory_queue_settings

logger = get_logger("Notification")

PUBLISH_TIMEOUT_MAX_ATTEMPTS = 3
PUBLISH_TIMEOUT_BASE_DELAY = 0.1


class NotificationQueue:
    async def claim(self, timeout: float | None = None):
        item = await self.dequeue(timeout=timeout)
        if item is None:
            return None

        async def acknowledge():
            return None

        async def release():
            await self.enqueue(item)

        return NotificationDelivery(item, acknowledge=acknowledge, retry=self.enqueue, release=release)

    async def enqueue(self, item: dict):
        raise NotImplementedError

    async def dequeue(self, timeout: float | None = None):
        raise NotImplementedError


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

        self._initialize_lock = asyncio.Lock()
        self._nc: nats.NATS | None = None
        self._js: JetStreamContext | None = None
        self._consumer: JetStreamContext.PullSubscription | None = None

    async def initialize(self, create_consumer: bool = True):
        """Serialize setup so concurrent callers cannot leak competing connections."""
        async with self._initialize_lock:
            await self._initialize(create_consumer)

    async def _initialize(self, create_consumer: bool):
        """Initialize NATS connection, JetStream stream, and optionally pull consumer.

        Args:
            create_consumer: If True (default), create/subscribe to the pull consumer.
                           If False, only initialize the stream for publishing.
                           Producer-only roles (e.g., backend) should pass False.
        """
        if not is_nats_enabled():
            raise RuntimeError("NATS is not enabled")

        if self._nc is not None and not self._nc.is_closed and self._js is not None:
            if create_consumer and self._consumer is None:
                self._consumer = await self._js.pull_subscribe(
                    subject=self.SUBJECT, durable=self.CONSUMER_NAME, stream=self.STREAM_NAME
                )
            return

        # Publish state only when initialization completes. A failed stream or
        # subscription setup must not leak a connection or look initialized.
        nc = await create_nats_client()
        if nc is None:
            raise RuntimeError("Failed to create NATS client")
        try:
            js = await get_jetstream_context(nc)
            try:
                await js.add_stream(name=self.STREAM_NAME, subjects=[self.SUBJECT])
            except nats.js.errors.APIError:
                # An existing stream can be reused, but permission/transport/
                # configuration failures must not be mistaken for its existence.
                await js.stream_info(self.STREAM_NAME)

            consumer = None
            if create_consumer:
                consumer = await js.pull_subscribe(
                    subject=self.SUBJECT, durable=self.CONSUMER_NAME, stream=self.STREAM_NAME
                )
        except BaseException:
            try:
                await asyncio.wait_for(nc.close(), timeout=3)
            except Exception as err:
                logger.warning("Failed to close notification setup connection (%s)", type(err).__name__)
            raise
        self._nc, self._js, self._consumer = nc, js, consumer

    async def enqueue(self, item: dict):
        """Add a notification item to the queue - persisted in JetStream."""
        if not self._js:
            raise RuntimeError("JetStream context not available")

        data = json.dumps(item).encode()
        for attempt in range(PUBLISH_TIMEOUT_MAX_ATTEMPTS):
            try:
                await self._js.publish(self.SUBJECT, data)
                return
            except (TimeoutError, nats_errors.TimeoutError) as err:
                if attempt == PUBLISH_TIMEOUT_MAX_ATTEMPTS - 1:
                    raise

                delay = PUBLISH_TIMEOUT_BASE_DELAY * (2**attempt)
                logger.warning(
                    f"NATS notification publish timed out, retrying in {delay:.1f}s "
                    f"(attempt {attempt + 1}/{PUBLISH_TIMEOUT_MAX_ATTEMPTS}): {err}"
                )
                await asyncio.sleep(delay)

    async def _fetch(self, timeout: float | None = None):
        """Get a notification item from the queue - messages are held until claimed."""
        if not self._consumer:
            raise RuntimeError("Consumer not available")

        timeout_seconds = timeout if timeout is not None else 1
        try:
            msgs = await self._consumer.fetch(1, timeout=timeout_seconds)
        except TimeoutError, nats_errors.TimeoutError:
            return None
        if not msgs:
            return None

        msg = msgs[0]
        try:
            data = json.loads(msg.data.decode())
            if not isinstance(data, dict):
                raise TypeError("Notification must be a JSON object")
        except ValueError, TypeError:
            # Retrying malformed wire data forever poisons the durable consumer.
            # Terminate this message without recording potentially secret payloads.
            logger.warning("Terminating malformed notification queue message")
            await msg.term()
            return None
        return msg, data

    async def claim(self, timeout: float | None = None):
        fetched = await self._fetch(timeout)
        if fetched is None:
            return None
        msg, data = fetched

        async def retry(item):
            await self.enqueue(item)
            await msg.ack_sync()

        async def release():
            await msg.nak(delay=1)

        return NotificationDelivery(
            data, acknowledge=msg.ack_sync, retry=retry, release=release, heartbeat=msg.in_progress
        )

    async def dequeue(self, timeout: float | None = None):
        """Legacy destructive pop. Production consumers must use claim instead."""
        fetched = await self._fetch(timeout)
        if fetched is None:
            return None
        msg, data = fetched
        await msg.ack()
        return data


class QueueOverloadedError(TimeoutError):
    """Explicit backpressure: caller must decide whether to retry or reject."""


class InMemoryNotificationQueue(NotificationQueue):
    def __init__(self, *, capacity=None, enqueue_timeout=None, max_item_bytes=None):
        self.capacity = memory_queue_settings.capacity if capacity is None else capacity
        self.enqueue_timeout = memory_queue_settings.enqueue_timeout if enqueue_timeout is None else enqueue_timeout
        self.max_item_bytes = memory_queue_settings.max_item_bytes if max_item_bytes is None else max_item_bytes
        if (
            not isinstance(self.capacity, int)
            or not isinstance(self.max_item_bytes, int)
            or self.capacity < 1
            or not math.isfinite(self.enqueue_timeout)
            or self.enqueue_timeout <= 0
            or self.max_item_bytes < 1
        ):
            raise ValueError("Queue limits must be positive")
        self.q: asyncio.Queue[dict] = asyncio.Queue(maxsize=self.capacity)
        # Reserve a slot until settlement, not merely until claim. Retries reuse
        # that reservation, so consumers cannot deadlock behind new producers.
        self._slots = asyncio.BoundedSemaphore(self.capacity)
        self._accepting = True
        self.inflight = 0

    def quiesce(self):
        self._accepting = False

    async def enqueue(self, item: dict):
        if not self._accepting:
            raise QueueOverloadedError("Notification queue is shutting down")
        if not isinstance(item, dict):
            raise TypeError("Notification must be an object")
        # Copy through JSON: caller mutations cannot bypass the payload limit.
        encoded = json.dumps(item, allow_nan=False).encode()
        if len(encoded) > self.max_item_bytes:
            raise ValueError("Notification exceeds the configured payload limit")
        snapshot = json.loads(encoded)
        try:
            async with asyncio.timeout(self.enqueue_timeout):
                await self._slots.acquire()
        except TimeoutError as err:
            raise QueueOverloadedError("Notification queue capacity exhausted") from err
        try:
            if not self._accepting:
                raise QueueOverloadedError("Notification queue is shutting down")
            self.q.put_nowait(snapshot)
        except BaseException:
            self._slots.release()
            raise

    async def _take(self, timeout):
        if timeout is None:
            return await self.q.get()
        if timeout <= 0:
            try:
                return self.q.get_nowait()
            except asyncio.QueueEmpty:
                return None
        try:
            return await asyncio.wait_for(self.q.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def claim(self, timeout: float | None = None):
        item = await self._take(timeout)
        if item is None:
            return None
        self.inflight += 1

        async def acknowledge():
            self.inflight -= 1
            self._slots.release()

        async def restore(value):
            # Reserved capacity guarantees space, even after quiesce.
            if not isinstance(value, dict):
                raise TypeError("Notification must be an object")
            encoded = json.dumps(value, allow_nan=False).encode()
            if len(encoded) > self.max_item_bytes:
                raise ValueError("Notification exceeds the configured payload limit")
            self.q.put_nowait(json.loads(encoded))
            self.inflight -= 1

        async def release():
            await restore(item)

        return NotificationDelivery(item, acknowledge=acknowledge, retry=restore, release=release)

    async def dequeue(self, timeout: float | None = None):
        """Legacy destructive pop; releases capacity immediately."""
        item = await self._take(timeout)
        if item is not None:
            self._slots.release()
        return item
