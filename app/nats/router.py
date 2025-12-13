import asyncio
import json
from typing import Callable

import nats

from app.nats.client import create_nats_client
from app.nats.message import MessageTopic, NatsMessage
from app.utils.logger import get_logger
from config import MULTI_WORKER, NATS_WORKER_SYNC_SUBJECT

logger = get_logger("nats-router")


class NatsMessageRouter:
    """Global NATS message router that routes messages to topic-specific handlers."""

    def __init__(self):
        self._nc: nats.NATS | None = None
        self._listener_task: asyncio.Task | None = None
        self._handlers: dict[MessageTopic, Callable[[dict], asyncio.coroutine]] = {}
        self._running = False

    async def _get_client(self) -> nats.NATS | None:
        """Get or create NATS client."""
        if not self._nc:
            self._nc = await create_nats_client()
        return self._nc

    def register_handler(self, topic: MessageTopic, handler: Callable[[dict], asyncio.coroutine]):
        """Register a handler function for a specific topic."""
        self._handlers[topic] = handler
        logger.debug(f"Registered handler for topic: {topic.value}")

    async def _listen(self):
        """Main listener loop that routes messages to handlers."""
        client = await self._get_client()
        if not client:
            return

        try:
            sub = await client.subscribe(NATS_WORKER_SYNC_SUBJECT)
            logger.debug(f"NATS message router started, listening on {NATS_WORKER_SYNC_SUBJECT}")

            async for msg in sub.messages:
                try:
                    data = msg.data.decode()
                    payload = json.loads(data)
                    message = NatsMessage.model_validate(payload)
                except Exception as exc:
                    logger.warning(f"Failed to parse NATS message: {exc}")
                    continue

                # Route to appropriate handler
                handler = self._handlers.get(message.topic)
                if handler:
                    try:
                        await handler(message.data)
                    except Exception as exc:
                        logger.error(f"Handler error for topic {message.topic.value}: {exc}", exc_info=True)
                else:
                    logger.warning(f"No handler registered for topic: {message.topic.value}")

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"NATS router listener stopped: {exc}", exc_info=True)
        finally:
            self._running = False
            logger.info("NATS message router stopped")

    async def start(self):
        """Start the router listener."""
        if not MULTI_WORKER:
            return

        if self._running:
            return

        if self._listener_task and not self._listener_task.done():
            return

        self._running = True
        self._listener_task = asyncio.create_task(self._listen())

    async def stop(self):
        """Stop the router listener."""
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await asyncio.wait_for(self._listener_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        if self._nc:
            await self._nc.close()
            self._nc = None

        self._running = False

    async def publish(self, topic: MessageTopic, data: dict):
        """Publish a message to NATS."""
        if not MULTI_WORKER:
            return

        client = await self._get_client()
        if not client:
            return

        try:
            message = NatsMessage(topic=topic, data=data)
            await client.publish(NATS_WORKER_SYNC_SUBJECT, message.model_dump_json().encode())
        except Exception as exc:
            logger.warning(f"Failed to publish NATS message: {exc}")


# Global router instance
router = NatsMessageRouter()
