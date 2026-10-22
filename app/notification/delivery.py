"""Explicit settlement for notification deliveries; no exactly-once promise."""

import asyncio
from contextlib import suppress

from app.utils.logger import get_logger

logger = get_logger("Notification")


class NotificationDelivery:
    def __init__(self, item, *, acknowledge, retry, release, heartbeat=None):
        self.item = item
        self._acknowledge = acknowledge
        self._retry = retry
        self._release = release
        self._heartbeat = heartbeat
        self._heartbeat_task = None
        self.settled = False

    async def acknowledge(self):
        if self.settled:
            return
        await self._acknowledge()
        self.settled = True
        await self._stop_heartbeat()

    async def retry(self, item):
        # NATS persists the replacement before acknowledging the original.
        if self.settled:
            return
        await self._retry(item)
        self.settled = True
        await self._stop_heartbeat()

    async def _stop_heartbeat(self):
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._heartbeat_task

    async def _keep_alive(self):
        while True:
            await asyncio.sleep(10)
            try:
                await self._heartbeat()
            except Exception as err:
                logger.warning("Notification lease heartbeat failed (%s)", type(err).__name__)

    async def __aenter__(self):
        if self._heartbeat is not None:
            self._heartbeat_task = asyncio.create_task(self._keep_alive(), name="notification-lease")
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        try:
            if not self.settled:
                try:
                    await self._release()
                    self.settled = True
                except Exception as err:
                    logger.error("Notification lease release failed (%s)", type(err).__name__)
                    if exc is None:
                        raise
        finally:
            await self._stop_heartbeat()
        return False
