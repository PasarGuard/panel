import asyncio
import sys
from contextlib import AsyncExitStack
from datetime import UTC, datetime as dt, timedelta as td
from itertools import count

import aiohttp
from pydantic import ValidationError
from sqlalchemy import delete

from app import on_shutdown, scheduler
from app.db import GetDB
from app.db.models import NotificationReminder
from app.lifecycle import ShutdownPhase
from app.models.settings import Webhook
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


# Bound memory use and let a busy producer yield to the next scheduled run.
MAX_NOTIFICATIONS_PER_RUN = 100
WEBHOOK_BATCH_SIZE = 50


async def send_to_all_webhooks(client: aiohttp.ClientSession, notifications, webhooks):
    """Return True if at least one webhook accepts the batch (not all recipients)."""
    if not notifications:
        return True

    async def send_one(webhook):
        headers = {"x-webhook-secret": webhook.secret} if webhook.secret else None
        try:
            async with client.post(webhook.url, json=notifications, headers=headers) as response:
                if response.status in (200, 201, 202, 204):
                    return True
                # URLs, response bodies and exception messages can contain secrets.
                logger.error("Webhook delivery failed: HTTP %s", response.status)
        except Exception as err:
            logger.error("Webhook request failed (%s)", type(err).__name__)
        return False

    results = await asyncio.gather(*(send_one(webhook) for webhook in webhooks))
    return any(results)


async def send_notifications(*, max_items: int | None = MAX_NOTIFICATIONS_PER_RUN):
    """Send a bounded batch; restore claimed, unfinished items on failure/cancellation.

    This is best-effort retry, not exactly-once delivery: a cancelled request may
    already have reached its recipient. Claims remain unacknowledged until settled.
    """
    settings: Webhook = await webhook_settings()
    if not settings.enable:
        return

    processed = 0
    pending: dict[int, WebhookNotification] = {}
    ready_notifications = []
    current_time = dt.now(UTC).timestamp()
    deliveries = {}

    async with AsyncExitStack() as leases:
        try:
            async with create_outbound_http_session(proxy=settings.proxy_url or None) as client:
                webhook_queue = get_webhook_queue()
                for _ in count() if max_items is None else range(max_items):
                    delivery = await webhook_queue.claim(timeout=1)
                    if delivery is None:
                        break
                    await leases.enter_async_context(delivery)
                    item = delivery.item
                    try:
                        notification = WebhookNotification.model_validate(item)
                    except ValidationError:
                        # Never requeue an undefined/stale variable or log its payload.
                        logger.warning("Discarding malformed webhook queue item")
                        await delivery.acknowledge()
                        continue

                    if notification.tries >= settings.recurrent:
                        await delivery.acknowledge()
                        continue
                    pending[id(notification)] = notification
                    deliveries[id(notification)] = delivery
                    if notification.send_at <= current_time:
                        ready_notifications.append(notification)

                for start in range(0, len(ready_notifications), WEBHOOK_BATCH_SIZE):
                    batch = ready_notifications[start : start + WEBHOOK_BATCH_SIZE]
                    success = await send_to_all_webhooks(client, [notif.payload for notif in batch], settings.webhooks)
                    retry_at = dt.now(UTC).timestamp() + settings.timeout
                    for notification in batch:
                        if success:
                            await deliveries[id(notification)].acknowledge()
                            pending.pop(id(notification))
                        else:
                            notification.tries += 1
                            if notification.tries >= settings.recurrent:
                                await deliveries[id(notification)].acknowledge()
                                pending.pop(id(notification))
                            else:
                                notification.send_at = retry_at
                    processed += len(batch)
        finally:
            # Preserve an in-flight exception/cancellation; attempt every requeue even
            # when one publish fails. NATS retains the original until replacement persistence and ack.
            active_error = sys.exception()
            errors = []
            for notification in pending.values():
                try:
                    await deliveries[id(notification)].retry(notification.model_dump())
                except Exception as err:
                    errors.append(err)
                    logger.error("Webhook requeue failed (%s)", type(err).__name__)
            if processed or pending:
                logger.info("Processed %s notifications; attempted %s requeues", processed, len(pending))
            if errors and active_error is None:
                raise ExceptionGroup("Webhook requeue failed", errors)


async def delete_expired_reminders() -> None:
    async with GetDB() as db:
        # Get current UTC time and convert to naive datetime
        now_utc = dt.now(tz=UTC)
        now_naive = now_utc.replace(tzinfo=None)

        result = await db.execute(delete(NotificationReminder).where(NotificationReminder.expires_at < now_naive))
        logger.info(f"Cleaned up {result.rowcount} expired reminders")


async def send_pending_notifications_before_shutdown():
    logger.info("Webhook final flush before shutdown")
    # Preserve the final drain: a normal-run cap must not silently abandon an
    # in-memory backlog on graceful shutdown. The supervisor owns the deadline.
    await send_notifications(max_items=None)


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
    on_shutdown(send_pending_notifications_before_shutdown, phase=ShutdownPhase.DRAIN)
    on_shutdown(shutdown_webhook_queue, phase=ShutdownPhase.TRANSPORTS)  # Must run after flush to keep queue alive
