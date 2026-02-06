import asyncio
from contextlib import suppress
from typing import Any

import httpx

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
from app.utils.logger import get_logger


client = None


async def define_client():
    """
    Re-create the global httpx.AsyncClient.
    Call this function after changing the proxy setting.
    """
    global client
    if client and not client.is_closed:
        asyncio.create_task(client.aclose())
    client = httpx.AsyncClient(
        http2=True,
        timeout=httpx.Timeout(10),
        proxy=(await notification_settings()).proxy_url,
    )


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
            if response.status_code in [200, 204]:
                logger.debug(f"Discord webhook payload delivered successfully, code {response.status_code}.")
                return True
            elif response.status_code == 429:
                retries += 1
                if retries < max_retries:
                    # Extract retry_after from response
                    try:
                        retry_after = response.json().get("retry_after", 0.5)
                    except Exception:
                        retry_after = 0.5
                    logger.warning(f"Discord rate limit hit, waiting {retry_after}s (attempt {retries}/{max_retries})")
                    await asyncio.sleep(retry_after)
                    continue
            else:
                response_text = response.text
                logger.error(f"Discord webhook failed: {response.status_code} - {response_text}")
                return False
        except Exception as err:
            logger.error(f"Discord webhook failed Exception: {str(err)}")
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
            if response.status_code == 200:
                logger.debug(f"Telegram message sent successfully, code {response.status_code}.")
                return True
            elif response.status_code == 429:
                retries += 1
                if retries < max_retries:
                    # Extract retry_after from Telegram response
                    try:
                        retry_after = response.json().get("parameters", {}).get("retry_after", 0.5)
                    except Exception:
                        retry_after = 0.5
                    logger.warning(f"Telegram rate limit hit, waiting {retry_after}s (attempt {retries}/{max_retries})")
                    await asyncio.sleep(retry_after)
                    continue
            else:
                response_text = response.text
                logger.error(f"Telegram message failed: {response.status_code} - {response_text}")
                return False
        except Exception as err:
            logger.error(f"Telegram message failed: {str(err)}")
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
        return

    success = await _send_discord_webhook_direct(
        json_data=notification.json_data, webhook=notification.webhook, max_retries=settings.max_retries
    )

    if success:
        logger.debug("Discord notification delivered")


async def _process_telegram_notification(notification: TelegramNotification):
    settings: NotificationSettings = await notification_settings()
    if not settings.notify_telegram or not settings.telegram_api_token:
        return

    success = await _send_telegram_message_direct(
        message=notification.message,
        chat_id=notification.chat_id,
        topic_id=notification.topic_id,
        max_retries=settings.max_retries,
        telegram_api_token=settings.telegram_api_token,
    )

    if success:
        logger.debug("Telegram notification delivered")


async def process_notification(item: dict | None):
    if not item:
        return

    try:
        match item.get("type"):
            case "discord":
                notification = DiscordNotification(**item)
                await _process_discord_notification(notification)
            case "telegram":
                notification = TelegramNotification(**item)
                await _process_telegram_notification(notification)
            case _:
                logger.warning(f"Unknown notification type received: {item}")
    except Exception as err:
        logger.error(f"Failed to process notification: {err}")


async def run_notification_dispatcher():
    queue = get_queue()
    while True:
        try:
            item: dict[str, Any] | None = await queue.dequeue(timeout=1)
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
