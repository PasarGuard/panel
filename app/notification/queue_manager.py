import asyncio
import json
from typing import Literal, Optional

import nats
from nats.js import api
from pydantic import BaseModel, Field

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client, get_jetstream_context


class NotificationQueue:
    async def enqueue(self, item: dict):
        raise NotImplementedError

    async def dequeue(self, timeout: int | None = None):
        raise NotImplementedError


class NatsNotificationQueue(NotificationQueue):
    STREAM_NAME = "NOTIFICATIONS"
    SUBJECT = "notifications.queue"
    CONSUMER_NAME = "notification_workers"

    def __init__(self):
        self._nc: nats.NATS | None = None
        self._js: api.JetStreamContext | None = None
        self._consumer: api.PullConsumer | None = None

    async def initialize(self):
        """Initialize NATS connection, JetStream stream, and pull consumer."""
        if not is_nats_enabled():
            raise RuntimeError("NATS is not enabled")

        self._nc = await create_nats_client()
        if not self._nc:
            raise RuntimeError("Failed to create NATS client")

        self._js = await get_jetstream_context(self._nc)

        # Create or get stream - messages are persisted here
        try:
            await self._js.add_stream(
                name=self.STREAM_NAME,
                subjects=[self.SUBJECT],
            )
        except Exception:
            # Stream already exists
            pass

        # Create or get durable pull consumer - all workers share the same consumer
        # This ensures each message is delivered to exactly one worker
        self._consumer = await self._js.pull_subscribe(
            subject=self.SUBJECT,
            durable=self.CONSUMER_NAME,
            stream=self.STREAM_NAME,
        )

    async def enqueue(self, item: dict):
        """Add a notification item to the queue - persisted in JetStream."""
        if not self._js:
            raise RuntimeError("JetStream context not available")

        data = json.dumps(item).encode()
        await self._js.publish(self.SUBJECT, data)

    async def dequeue(self, timeout: int | None = None):
        """Get a notification item from the queue - messages are held until claimed."""
        if not self._consumer:
            raise RuntimeError("Consumer not available")

        try:
            timeout_seconds = timeout if timeout is not None else 1
            msgs = await self._consumer.fetch(1, timeout=timeout_seconds)
            if msgs:
                msg = msgs[0]
                try:
                    data = json.loads(msg.data.decode())
                    await msg.ack()
                    return data
                except Exception:
                    await msg.nak()  # Negative ack on parse error
                    return None
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None

        return None


class InMemoryNotificationQueue(NotificationQueue):
    def __init__(self):
        self.q: asyncio.Queue[dict] = asyncio.Queue()

    async def enqueue(self, item: dict):
        await self.q.put(item)

    async def dequeue(self, timeout: int | None = None):
        if timeout:
            try:
                return await asyncio.wait_for(self.q.get(), timeout=timeout)
            except asyncio.TimeoutError:
                return None
        return await self.q.get()


class TelegramNotification(BaseModel):
    """Model for Telegram notification queue items"""

    type: Literal["telegram"] = Field(default="telegram")
    message: str
    chat_id: Optional[int] = Field(default=None)
    topic_id: Optional[int] = Field(default=None)
    tries: int = Field(default=0)


class DiscordNotification(BaseModel):
    """Model for Discord notification queue items"""

    type: Literal["discord"] = Field(default="discord")
    json_data: dict
    webhook: str
    tries: int = Field(default=0)


queue_instance: NotificationQueue | None = None


def get_queue() -> NotificationQueue:
    global queue_instance
    if queue_instance is None:
        queue_instance = NatsNotificationQueue() if is_nats_enabled() else InMemoryNotificationQueue()
    return queue_instance


async def initialize_queue():
    """Initialize the notification queue if it's a NATS queue."""
    queue = get_queue()
    if isinstance(queue, NatsNotificationQueue):
        await queue.initialize()


async def shutdown_queue():
    """Close NATS connection on shutdown."""
    queue = get_queue()
    if isinstance(queue, NatsNotificationQueue):
        if queue._nc:
            await queue._nc.close()


async def enqueue_telegram(message: str, chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> None:
    """Add a Telegram notification to the queue"""
    notification = TelegramNotification(message=message, chat_id=chat_id, topic_id=topic_id)
    await get_queue().enqueue(notification.model_dump())


async def enqueue_discord(json_data: dict, webhook: str) -> None:
    """Add a Discord notification to the queue"""
    notification = DiscordNotification(json_data=json_data, webhook=webhook)
    await get_queue().enqueue(notification.model_dump())
