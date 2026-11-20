import asyncio
import json
import random
from collections.abc import Awaitable, Callable

import nats

from app.nats.client import create_nats_client
from app.nats.message import MessageTopic, NatsMessage
from app.utils.logger import get_logger
from config import nats_settings, runtime_settings, server_settings

logger = get_logger("nats-router")


def _router_enabled() -> bool:
    multi_worker = runtime_settings.role.requires_nats or server_settings.workers > 1
    return nats_settings.enabled and multi_worker


class NatsMessageRouter:
    """Global NATS message router that routes messages to topic-specific handlers."""

    # Reconnects of a flapping link (and of all workers at once) are merged into one resync
    RESYNC_DELAY = 2.0
    RESYNC_JITTER = 3.0
    RESYNC_RETRY_DELAY = 30.0

    def __init__(self):
        self._nc: nats.NATS | None = None
        self._listener_task: asyncio.Task | None = None
        self._handlers: dict[MessageTopic, Callable[[dict], Awaitable[None]]] = {}
        self._resync_handlers: dict[MessageTopic, Callable[[], Awaitable[None]]] = {}
        self._dispatch_locks: dict[MessageTopic, asyncio.Lock] = {}
        self._resync_task: asyncio.Task | None = None
        self._resync_pending = False
        self._running = False

    async def _get_client(self) -> nats.NATS | None:
        """Get or create NATS client."""
        if not self._nc:
            self._nc = await create_nats_client(reconnected_cb=self._on_reconnected)
        return self._nc

    def register_handler(self, topic: MessageTopic, handler: Callable[[dict], Awaitable[None]]):
        """Register a handler function for a specific topic."""
        self._handlers[topic] = handler
        logger.debug(f"Registered handler for topic: {topic.value}")

    def register_resync_handler(self, topic: MessageTopic, handler: Callable[[], Awaitable[None]]):
        """Register how a topic's state is rebuilt from the database after a NATS reconnect."""
        self._resync_handlers[topic] = handler

    def _dispatch_lock(self, topic: MessageTopic) -> asyncio.Lock:
        # Messages of a topic wait while that topic is rebuilt, so a change that arrives meanwhile
        # is applied on top of the database snapshot instead of being overwritten by it. Hosts are
        # prepared from core inbounds, so the two share a lock; other topics are not held up.
        key = MessageTopic.CORE if topic is MessageTopic.HOST else topic
        return self._dispatch_locks.setdefault(key, asyncio.Lock())

    async def _on_reconnected(self):
        # worker_sync is fire-and-forget: whatever was published while this connection was
        # down (or before the publisher's buffered messages reached the server) is gone.
        self.request_resync()

    def request_resync(self):
        """Schedule one rebuild of the synced state; repeated requests are merged."""
        self._resync_pending = True
        if self._resync_task is None or self._resync_task.done():
            self._resync_task = asyncio.create_task(self._run_resync())

    async def _run_resync(self):
        delay = self.RESYNC_DELAY
        failed: set[MessageTopic] = set()
        while self._resync_pending or failed:
            await asyncio.sleep(delay + random.uniform(0, self.RESYNC_JITTER))
            if self._resync_pending:
                self._resync_pending = False
                topics = set(self._resync_handlers)
                logger.info("Reloading worker state from the database after NATS reconnect")
            else:
                # e.g. the database is unreachable too: retry what failed instead of keeping stale state
                topics = set(failed)
                if MessageTopic.CORE in topics:
                    topics.add(MessageTopic.HOST)
            failed = await self._resync(topics, previously_failed=failed)
            delay = self.RESYNC_RETRY_DELAY if failed else self.RESYNC_DELAY

    async def _resync(self, topics: set[MessageTopic], previously_failed: set[MessageTopic]) -> set[MessageTopic]:
        failed: set[MessageTopic] = set()
        # MessageTopic order: cores before hosts, which are prepared from core inbounds
        for topic in MessageTopic:
            handler = self._resync_handlers.get(topic)
            if handler is None or topic not in topics:
                continue
            try:
                async with self._dispatch_lock(topic):
                    await handler()
            except Exception as exc:
                failed.add(topic)
                if topic in previously_failed:
                    logger.warning(f"Resync for topic {topic.value} still failing, retrying later: {exc!r}")
                else:
                    logger.exception(f"Resync failed for topic {topic.value}")
        return failed

    async def _listen(self):
        """Main listener loop that routes messages to handlers."""
        client = await self._get_client()
        if not client:
            return

        try:
            sub = await client.subscribe(nats_settings.worker_sync_subject)
            logger.debug(f"NATS message router started, listening on {nats_settings.worker_sync_subject}")

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
                        async with self._dispatch_lock(message.topic):
                            await handler(message.data)
                    except Exception:
                        logger.exception(f"Handler error for topic {message.topic.value}")
                else:
                    logger.warning(f"No handler registered for topic: {message.topic.value}")

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("NATS router listener stopped")
        finally:
            self._running = False
            logger.info("NATS message router stopped")

    async def start(self):
        """Start the router listener."""
        if not _router_enabled():
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
            except TimeoutError, asyncio.CancelledError:
                pass

        if self._resync_task and not self._resync_task.done():
            self._resync_task.cancel()
        self._resync_task = None
        self._resync_pending = False

        if self._nc:
            await self._nc.close()
            self._nc = None

        self._running = False

    async def publish(self, topic: MessageTopic, data: dict):
        """Publish a message to NATS."""
        if not _router_enabled():
            return

        client = await self._get_client()
        if not client:
            return

        try:
            message = NatsMessage(topic=topic, data=data)
            await client.publish(nats_settings.worker_sync_subject, message.model_dump_json().encode())
        except Exception as exc:
            logger.warning(f"Failed to publish NATS message: {exc}")


# Global router instance
router = NatsMessageRouter()
