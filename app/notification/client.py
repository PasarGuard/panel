import asyncio
import json
import math
import time
import weakref
from contextlib import suppress
from dataclasses import dataclass

import aiohttp
from pydantic import ValidationError

from app import on_startup
from app.models.settings import NotificationSettings
from app.notification.nats_queue import NotificationDelivery
from app.notification.queue_manager import (
    DiscordNotification,
    TelegramNotification,
    enqueue_discord,
    enqueue_telegram,
    get_queue,
)
from app.settings import notification_settings
from app.utils.http_client import create_outbound_http_session
from app.utils.logger import get_logger

client: aiohttp.ClientSession | None = None


async def define_client():
    """
    Re-create the global aiohttp.ClientSession.
    Call this function after changing the proxy setting.
    """
    global client
    if client and not client.closed:
        asyncio.create_task(client.close())
    settings = await notification_settings()
    proxy_url = settings.proxy_url
    client = create_outbound_http_session(proxy=proxy_url if proxy_url else None)


on_startup(define_client)

logger = get_logger("Notification")


class RateLimitedError(Exception):
    """The destination answered 429 and asked to wait retry_after seconds."""

    def __init__(self, retry_after: float):
        super().__init__(retry_after)
        self.retry_after = retry_after


async def _post_notification(url: str, **kwargs) -> tuple[bool, float]:
    """Attempt once; queue delays keep rate-limited destinations off the worker."""
    async with client.post(url, **kwargs) as response:
        if response.status in (200, 204):
            return True, 0
        if response.status == 429:
            try:
                body_bytes = bytearray()
                async for chunk in response.content.iter_chunked(1024):
                    body_bytes.extend(chunk)
                    if len(body_bytes) > 4096:
                        raise ValueError("Rate-limit response is too large")
                body = json.loads(body_bytes)
                delay = float(body.get("parameters", body).get("retry_after", 1))
                if math.isfinite(delay):
                    raise RateLimitedError(max(1, min(delay, 3600)))
            except ValueError, TypeError, AttributeError:
                pass
        logger.warning("Notification delivery failed with HTTP %s", response.status)
    return False, 1


async def send_discord_webhook(json_data, webhook: str | None):
    """Enqueue Discord notification for processing"""
    if not webhook:
        return
    await enqueue_discord(json_data, webhook)


async def send_telegram_message(message, chat_id: int | None = None, topic_id: int | None = None):
    """
    Enqueue a Telegram message for processing.
    Args:
        message (str): The message to send
        chat_id (int, optional): The chat ID (can be user, group, or channel)
        topic_id (int, optional): The topic ID for forum topics (only with chat_id)
    """
    if not chat_id:
        return
    await enqueue_telegram(message, chat_id, topic_id)


# Telegram limits messages per chat and Discord per webhook. After a 429 the
# destination gets a schedule: each message to it takes the next slot (kept on
# the queued item), and every later 429 moves the whole schedule back. Waiting
# messages keep their order, and other destinations are not held up.
RATE_LIMIT_SPACING = 1.0  # seconds between slots: Telegram asks for at most one message a second per chat
RATE_LIMIT_IDLE = 60.0  # forget a schedule this long after its last slot


@dataclass
class _RateLimit:
    first_slot: float
    next_slot: float
    offset: float = 0.0  # added to a slot to get its send time


_rate_limits: dict[str, _RateLimit] = {}
# One delivery at a time per destination, so a 429 is seen before the next send.
_destination_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def _destination_lock(destination: str) -> asyncio.Lock:
    lock = _destination_locks.get(destination)
    if lock is None:
        lock = _destination_locks[destination] = asyncio.Lock()
    return lock


def _rate_limit(destination: str, now: float) -> _RateLimit | None:
    for key, limit in list(_rate_limits.items()):
        if limit.next_slot + limit.offset + RATE_LIMIT_IDLE < now:
            del _rate_limits[key]
    return _rate_limits.get(destination)


def _take_slot(limit: _RateLimit, notification: TelegramNotification | DiscordNotification, now: float) -> float:
    """Return the notification's slot, giving it the next free one if it has none in this schedule."""
    if notification.slot is not None and notification.slot >= limit.first_slot:
        return notification.slot
    slot = max(limit.next_slot, now - limit.offset)
    limit.next_slot = slot + RATE_LIMIT_SPACING
    return slot


async def process_notification(delivery: NotificationDelivery):
    async with delivery:
        item = delivery.data
        try:
            match item.get("type"):
                case "discord":
                    notification = DiscordNotification.model_validate(item)
                case "telegram":
                    notification = TelegramNotification.model_validate(item)
                case _:
                    logger.warning("Discarding unknown notification type")
                    await delivery.ack()
                    return
        except ValidationError:
            logger.error("Discarding malformed notification")
            await delivery.ack()
            return

        settings: NotificationSettings = await notification_settings()
        if notification.tries >= settings.max_retries:
            await delivery.ack()
            return
        delay = notification.send_at - time.time()
        if delay > 0:
            await delivery.release(delay)
            return

        if isinstance(notification, DiscordNotification):
            if not settings.notify_discord:
                await delivery.ack()
                return
            destination = f"discord:{notification.webhook}"
        else:
            if not settings.notify_telegram or not settings.telegram_api_token or not notification.chat_id:
                await delivery.ack()
                return
            destination = f"telegram:{notification.chat_id}"

        async with _destination_lock(destination):
            now = time.time()
            limit = _rate_limit(destination, now)
            if limit is not None:
                slot = _take_slot(limit, notification, now)
                send_at = slot + limit.offset
                # A message that just took its slot, or whose slot a later 429 moved back, goes
                # behind the messages ahead of it in the queue even when its time has come.
                if slot != notification.slot or notification.send_at < send_at:
                    scheduled = notification.model_copy(update={"slot": slot, "send_at": send_at})
                    try:
                        await delivery.retry(scheduled.model_dump(), delay=send_at - now)
                    except asyncio.QueueFull:
                        # No room to keep the slot: come back then and take a new one.
                        await delivery.release(send_at - now)
                    return

            try:
                await delivery.prepare(notification.model_dump())
                if isinstance(notification, DiscordNotification):
                    success, delay = await _post_notification(notification.webhook, json=notification.json_data)
                else:
                    payload = {"parse_mode": "HTML", "text": notification.message, "chat_id": notification.chat_id}
                    if notification.topic_id:
                        payload["message_thread_id"] = notification.topic_id
                    success, delay = await _post_notification(
                        f"https://api.telegram.org/bot{settings.telegram_api_token}/sendMessage", data=payload
                    )
            except RateLimitedError as error:
                # Not a failed attempt: wait as asked, and move the rest of the schedule back with it.
                now = time.time()
                limit = _rate_limits.get(destination)
                if limit is None:
                    limit = _rate_limits[destination] = _RateLimit(first_slot=now, next_slot=now)
                slot = _take_slot(limit, notification, now)
                limit.offset = max(limit.offset, now + error.retry_after - slot)
                retry = notification.model_copy(update={"slot": slot, "send_at": slot + limit.offset})
                await delivery.retry(retry.model_dump(), delay=retry.send_at - now)
                return
            except aiohttp.ClientError, TimeoutError:
                logger.warning("Notification delivery failed due to a connection error or timeout")
                success, delay = False, 1

            if success or notification.tries + 1 >= settings.max_retries:
                if not success:
                    logger.warning("Notification exhausted its delivery attempts")
                await delivery.ack()
            else:
                retry = notification.model_copy(
                    update={"tries": notification.tries + 1, "send_at": time.time() + delay}
                )
                await delivery.retry(retry.model_dump(), delay=delay)


async def run_notification_dispatcher():
    queue = get_queue()
    while True:
        try:
            item = await queue.dequeue(timeout=1)
            if item:
                await process_notification(item)
        except asyncio.CancelledError:
            break
        except Exception as err:
            logger.error(f"Notification dispatcher error: {err}")
            await asyncio.sleep(1)


dispatcher_task: asyncio.Task | None = None


async def start_notification_dispatcher():
    global dispatcher_task
    if dispatcher_task is None:
        dispatcher_task = asyncio.create_task(run_notification_dispatcher())


async def stop_notification_dispatcher():
    global dispatcher_task
    if dispatcher_task is None:
        return

    dispatcher_task.cancel()
    with suppress(asyncio.CancelledError):
        await dispatcher_task
    dispatcher_task = None
