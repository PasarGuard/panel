import asyncio
from contextlib import AsyncExitStack
from datetime import UTC, datetime as dt, timedelta as td

import aiohttp
from pydantic import ValidationError
from sqlalchemy import delete

from app import on_shutdown, scheduler
from app.db import GetDB
from app.db.models import NotificationReminder
from app.models.settings import Webhook, WebhookInfo
from app.notification.nats_queue import NotificationDelivery
from app.notification.queue_manager import (
    WebhookNotification,
    get_webhook_queue,
    shutdown_webhook_queue,
)
from app.settings import webhook_settings
from app.utils.http_client import create_outbound_http_session
from app.utils.logger import get_logger
from config import job_settings, runtime_settings

logger = get_logger("send-notification")


BATCH_SIZE = 50
MAX_BATCHES_PER_RUN = 10
WEBHOOK_CONCURRENCY = 8


async def _send_webhook(client: aiohttp.ClientSession, webhook: WebhookInfo, payloads: list[dict]) -> bool:
    headers = {"x-webhook-secret": webhook.secret} if webhook.secret else None
    try:
        async with client.post(webhook.url, json=payloads, headers=headers) as response:
            if response.status in (200, 201, 202, 204):
                return True
            # Response bodies and URLs can contain credentials or unbounded data.
            logger.warning("Webhook delivery failed with HTTP %s", response.status)
    except aiohttp.ClientError, TimeoutError:
        logger.warning("Webhook delivery failed due to a connection error or timeout")
    return False


async def _send_batch(
    client: aiohttp.ClientSession, settings: Webhook, batch: list[tuple[NotificationDelivery, WebhookNotification]]
):
    webhooks = {webhook.url: webhook for webhook in settings.webhooks}
    pending = {}
    for delivery, notification in batch:
        targets = notification.pending_webhooks
        pending[delivery] = set(webhooks if targets is None else targets).intersection(webhooks)

    async def send_one(url):
        payloads = [notification.payload for delivery, notification in batch if url in pending[delivery]]
        if payloads and await _send_webhook(client, webhooks[url], payloads):
            for delivery, _ in batch:
                pending[delivery].discard(url)

    # Limit both live requests and tasks even with many configured destinations.
    urls = list(webhooks)
    for start in range(0, len(urls), WEBHOOK_CONCURRENCY):
        async with asyncio.TaskGroup() as tasks:
            for url in urls[start : start + WEBHOOK_CONCURRENCY]:
                tasks.create_task(send_one(url))

    retry_at = dt.now(UTC).timestamp() + settings.timeout
    for delivery, notification in batch:
        failed = pending[delivery]
        if failed and notification.tries + 1 < settings.recurrent:
            retry = notification.model_copy(
                update={"pending_webhooks": sorted(failed), "tries": notification.tries + 1, "send_at": retry_at}
            )
            # Persist failed destinations before acknowledging the original.
            await delivery.retry(retry.model_dump(), delay=settings.timeout)
        else:
            if failed:
                logger.warning("Webhook notification exhausted its delivery attempts for %s destinations", len(failed))
            await delivery.ack()


async def send_notifications():
    """Deliver bounded batches while retaining ownership until delivery/retry is safe."""
    settings: Webhook = await webhook_settings()
    if not settings.enable:
        return

    queue = get_webhook_queue()
    async with create_outbound_http_session(proxy=settings.proxy_url or None) as client:
        for _ in range(MAX_BATCHES_PER_RUN):
            async with AsyncExitStack() as reservations:
                batch = []
                exhausted = False
                for _ in range(BATCH_SIZE):
                    delivery = await queue.dequeue(timeout=0.05)
                    if delivery is None:
                        exhausted = True
                        break
                    await reservations.enter_async_context(delivery)
                    try:
                        notification = WebhookNotification.model_validate(delivery.data)
                    except ValidationError:
                        logger.error("Discarding malformed webhook notification")
                        await delivery.ack()
                        continue
                    if notification.tries >= settings.recurrent:
                        await delivery.ack()
                        continue
                    delay = notification.send_at - dt.now(UTC).timestamp()
                    if delay > 0:
                        await delivery.release(delay=delay)
                        continue
                    batch.append((delivery, notification))
                if batch:
                    await _send_batch(client, settings, batch)
                if exhausted:
                    break


async def delete_expired_reminders() -> None:
    async with GetDB() as db:
        # Get current UTC time and convert to naive datetime
        now_utc = dt.now(tz=UTC)
        now_naive = now_utc.replace(tzinfo=None)

        result = await db.execute(delete(NotificationReminder).where(NotificationReminder.expires_at < now_naive))
        logger.info(f"Cleaned up {result.rowcount} expired reminders")


async def send_pending_notifications_before_shutdown():
    logger.info("Webhook final flush before shutdown")
    await send_notifications()


if runtime_settings.role.runs_scheduler:
    scheduler.add_job(
        send_notifications,
        "interval",
        seconds=job_settings.send_notifications_interval,
        max_instances=1,
        coalesce=True,
        id="send_notifications",
        replace_existing=True,
    )
    scheduler.add_job(
        delete_expired_reminders,
        "interval",
        hours=6,
        start_date=dt.now(UTC) + td(minutes=5),
        id="delete_expired_notification_reminders",
        replace_existing=True,
    )
    on_shutdown(send_pending_notifications_before_shutdown)
    on_shutdown(shutdown_webhook_queue)  # Must run after flush to keep queue alive
