import asyncio
import json
import math
import time
from contextlib import suppress

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
                    return False, max(1, min(delay, 3600))
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

        try:
            if isinstance(notification, DiscordNotification):
                if not settings.notify_discord:
                    await delivery.ack()
                    return
                success, delay = await _post_notification(notification.webhook, json=notification.json_data)
            else:
                if not settings.notify_telegram or not settings.telegram_api_token or not notification.chat_id:
                    await delivery.ack()
                    return
                payload = {"parse_mode": "HTML", "text": notification.message, "chat_id": notification.chat_id}
                if notification.topic_id:
                    payload["message_thread_id"] = notification.topic_id
                success, delay = await _post_notification(
                    f"https://api.telegram.org/bot{settings.telegram_api_token}/sendMessage", data=payload
                )
        except aiohttp.ClientError, TimeoutError:
            logger.warning("Notification delivery failed due to a connection error or timeout")
            success, delay = False, 1

        if success or notification.tries + 1 >= settings.max_retries:
            if not success:
                logger.warning("Notification exhausted its delivery attempts")
            await delivery.ack()
        else:
            retry = notification.model_copy(update={"tries": notification.tries + 1, "send_at": time.time() + delay})
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
