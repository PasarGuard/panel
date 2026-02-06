import asyncio
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.nats import is_nats_enabled
from app.notification.nats_queue import NatsNotificationQueue, InMemoryNotificationQueue, NotificationQueue
from config import (
    ROLE,
    NATS_NOTIFICATION_STREAM,
    NATS_NOTIFICATION_SUBJECT,
    NATS_NOTIFICATION_CONSUMER,
    NATS_WEBHOOK_STREAM,
    NATS_WEBHOOK_SUBJECT,
    NATS_WEBHOOK_CONSUMER,
)


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


class WebhookNotification(BaseModel):
    """Model for Webhook notification queue items"""

    type: Literal["webhook"] = Field(default="webhook")
    payload: dict  # the jsonable_encoder'd notification (what gets POSTed to webhook URLs)
    send_at: float  # when to send (for delayed retry)
    tries: int = Field(default=0)


# Telegram/Discord queue singleton
queue_instance: NotificationQueue = (
    NatsNotificationQueue(
        stream_name=NATS_NOTIFICATION_STREAM,
        subject=NATS_NOTIFICATION_SUBJECT,
        consumer_name=NATS_NOTIFICATION_CONSUMER,
    )
    if is_nats_enabled()
    else InMemoryNotificationQueue()
)


# Webhook queue singleton
webhook_queue_instance: NotificationQueue = (
    NatsNotificationQueue(
        stream_name=NATS_WEBHOOK_STREAM,
        subject=NATS_WEBHOOK_SUBJECT,
        consumer_name=NATS_WEBHOOK_CONSUMER,
    )
    if is_nats_enabled()
    else InMemoryNotificationQueue()
)


def get_queue() -> NotificationQueue:
    return queue_instance


async def init_queue(queue: NotificationQueue):
    if isinstance(queue, NatsNotificationQueue):
        # Only scheduler role (and all-in-one) actually dequeue and need the consumer
        await queue.initialize(create_consumer=ROLE.runs_scheduler)


async def initialize_queues():
    """Initialize the notification queue if it's a NATS queue.

    Producers (backend, node) only need the stream for publishing.
    Consumers (scheduler) need the full consumer subscription.
    """

    await init_queue(queue_instance)
    await init_queue(webhook_queue_instance)


async def shutdown_queue(queue: NotificationQueue):
    """Close NATS connection on shutdown."""
    if isinstance(queue, NatsNotificationQueue):
        try:
            if queue._consumer:
                await queue._consumer.unsubscribe()
        except Exception:
            pass

        if queue._nc and not queue._nc.is_closed:
            try:
                await asyncio.wait_for(queue._nc.close(), timeout=3)
            except asyncio.TimeoutError:
                # Don't block shutdown if NATS is slow to close
                pass
            except Exception:
                pass

        queue._consumer = None
        queue._js = None
        queue._nc = None


async def shutdown_webhook_queue():
    await shutdown_queues(webhook_queue_instance)


async def shutdown_queues():
    await shutdown_queue(queue_instance)


def get_webhook_queue() -> NotificationQueue:
    return webhook_queue_instance


async def enqueue_telegram(message: str, chat_id: Optional[int] = None, topic_id: Optional[int] = None) -> None:
    """Add a Telegram notification to the queue"""
    notification = TelegramNotification(message=message, chat_id=chat_id, topic_id=topic_id)
    await get_queue().enqueue(notification.model_dump())


async def enqueue_discord(json_data: dict, webhook: str) -> None:
    """Add a Discord notification to the queue"""
    notification = DiscordNotification(json_data=json_data, webhook=webhook)
    await get_queue().enqueue(notification.model_dump())


async def enqueue_webhook(payload: dict, send_at: float | None = None, tries: int = 0) -> None:
    """Add a webhook notification to the queue"""
    import time

    notification = WebhookNotification(
        payload=payload,
        send_at=send_at if send_at is not None else time.time(),
        tries=tries,
    )
    await get_webhook_queue().enqueue(notification.model_dump())
