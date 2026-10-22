import asyncio
from contextlib import suppress

import aiohttp
from pydantic import ValidationError

from app import on_startup
from app.models.settings import NotificationSettings
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


_client_lock = asyncio.Lock()


async def define_client():
    """Replace the HTTP session only after settings and replacement are ready."""
    global client
    async with _client_lock:
        settings = await notification_settings()
        replacement = create_outbound_http_session(proxy=settings.proxy_url or None)
        previous = client
        client = replacement
        if previous and not previous.closed:
            await previous.close()


async def close_notification_client():
    global client
    async with _client_lock:
        previous = client
        client = None
        if previous and not previous.closed:
            await previous.close()


on_startup(define_client)

logger = get_logger("Notification")


async def _send_discord_webhook_direct(json_data, webhook, max_retries: int) -> bool:
    """
    Internal function to send Discord webhook with proper retry_after handling.
    Returns True if successful, False otherwise.
    """
    retries = 0
    while retries < max_retries:
        try:
            response = await client.post(webhook, json=json_data)
            if response.status in [200, 204]:
                logger.debug(f"Discord webhook payload delivered successfully, code {response.status}.")
                return True
            elif response.status == 429:
                retries += 1
                if retries < max_retries:
                    # Extract retry_after from response
                    try:
                        retry_after = (await response.json()).get("retry_after", 0.5)
                    except Exception:
                        retry_after = 0.5
                    logger.warning(f"Discord rate limit hit, waiting {retry_after}s (attempt {retries}/{max_retries})")
                    await asyncio.sleep(retry_after)
                    continue
            else:
                response_text = await response.text()
                logger.error(f"Discord webhook failed: {response.status} - {response_text}")
                return False
        except Exception as err:
            logger.error(f"Discord webhook failed Exception: {err!s}")
            return False

    logger.error(f"Discord webhook failed after {max_retries} retries")
    return False


async def send_discord_webhook(json_data, webhook: str | None):
    """Enqueue Discord notification for processing"""
    if not webhook:
        return
    await enqueue_discord(json_data, webhook)


async def _send_telegram_message_direct(
    message: str,
    chat_id: int | None,
    topic_id: int | None,
    max_retries: int,
    telegram_api_token: str,
) -> bool:
    """
    Internal function to send Telegram message with proper retry_after handling.
    Returns True if successful, False otherwise.
    """
    base_url = f"https://api.telegram.org/bot{telegram_api_token}/sendMessage"
    payload = {"parse_mode": "HTML", "text": message}

    # Validate chat_id is provided
    if not chat_id:
        logger.error("chat_id is required")
        return False

    # Set chat_id and optional topic_id
    payload["chat_id"] = chat_id
    if topic_id:
        payload["message_thread_id"] = topic_id

    retries = 0
    while retries < max_retries:
        try:
            response = await client.post(base_url, data=payload)
            if response.status == 200:
                logger.debug(f"Telegram message sent successfully, code {response.status}.")
                return True
            elif response.status == 429:
                retries += 1
                if retries < max_retries:
                    # Extract retry_after from Telegram response
                    try:
                        retry_after = (await response.json()).get("parameters", {}).get("retry_after", 0.5)
                    except Exception:
                        retry_after = 0.5
                    logger.warning(f"Telegram rate limit hit, waiting {retry_after}s (attempt {retries}/{max_retries})")
                    await asyncio.sleep(retry_after)
                    continue
            else:
                response_text = await response.text()
                logger.error(f"Telegram message failed: {response.status} - {response_text}")
                return False
        except Exception as err:
            logger.error(f"Telegram message failed: {err!s}")
            return False

    logger.error(f"Telegram message failed after {max_retries} retries")
    return False


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


async def _process_discord_notification(notification: DiscordNotification):
    settings: NotificationSettings = await notification_settings()
    if not settings.notify_discord:
        return True

    success = await _send_discord_webhook_direct(
        json_data=notification.json_data, webhook=notification.webhook, max_retries=settings.max_retries
    )

    if success:
        logger.debug("Discord notification delivered")
    return success


async def _process_telegram_notification(notification: TelegramNotification):
    settings: NotificationSettings = await notification_settings()
    if not settings.notify_telegram or not settings.telegram_api_token:
        return True

    success = await _send_telegram_message_direct(
        message=notification.message,
        chat_id=notification.chat_id,
        topic_id=notification.topic_id,
        max_retries=settings.max_retries,
        telegram_api_token=settings.telegram_api_token,
    )

    if success:
        logger.debug("Telegram notification delivered")
    return success


async def process_notification(item: dict | None):
    """Return True for delivered/disabled/invalid items, False for transient failure."""
    if not item:
        return True
    try:
        match item.get("type"):
            case "discord":
                return await _process_discord_notification(DiscordNotification(**item))
            case "telegram":
                return await _process_telegram_notification(TelegramNotification(**item))
            case _:
                logger.warning("Discarding unknown notification type")
                return True
    except ValidationError:
        logger.warning("Discarding malformed notification")
        return True
    except Exception as err:
        logger.error("Failed to process notification (%s)", type(err).__name__)
        return False


async def consume_notification(queue, *, timeout=1):
    delivery = await queue.claim(timeout=timeout)
    if delivery is None:
        return False
    async with delivery:
        if await process_notification(delivery.item):
            await delivery.acknowledge()
        else:
            tries = delivery.item.get("tries", 0)
            # Malformed retry metadata must not create an infinite delivery loop.
            if not isinstance(tries, int) or tries < 0 or tries >= 2:
                logger.error("Notification delivery attempts exhausted")
                await delivery.acknowledge()
            else:
                await delivery.retry({**delivery.item, "tries": tries + 1})
    return True


async def run_notification_dispatcher():
    queue = get_queue()
    while True:
        try:
            await consume_notification(queue)
        except asyncio.CancelledError:
            break
        except Exception as err:
            logger.error("Notification dispatcher error (%s)", type(err).__name__)
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
