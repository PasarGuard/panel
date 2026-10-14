import asyncio
import contextlib
import json
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

import nats

from app.nats.client import create_nats_client, get_or_create_kv_bucket
from app.nats.message import MessageTopic, NatsMessage
from app.utils.logger import get_logger
from config import nats_settings, runtime_settings, server_settings

logger = get_logger("nats-router")
RECONCILE_INTERVAL = 5.0
DATABASE_RECONCILE_INTERVAL = 30.0
TOPIC_QUEUE_LIMIT = 256


def _router_enabled() -> bool:
    multi_worker = runtime_settings.role.requires_nats or server_settings.workers > 1
    return nats_settings.enabled and multi_worker


class NatsMessageRouter:
    """Ordered, bounded topic consumers with durable invalidation checkpoints."""

    def __init__(self):
        self._nc: nats.NATS | None = None
        self._kv = None
        self._client_lock = asyncio.Lock()
        self._listener_task: asyncio.Task | None = None
        self._reconcile_task: asyncio.Task | None = None
        self._handlers: dict[MessageTopic, Callable[[dict], Awaitable[None]]] = {}
        self._reconcilers: dict[MessageTopic, Callable[[dict], Awaitable[None]]] = {}
        self._queues: dict[MessageTopic, asyncio.Queue] = {}
        self._topic_tasks: dict[MessageTopic, asyncio.Task] = {}
        self._seen: dict[MessageTopic, str] = {}
        self._dirty: set[MessageTopic] = set()
        self._refresh_pending: set[MessageTopic] = set()
        self._ready = asyncio.Event()
        self._running = False

    async def _get_client(self) -> nats.NATS | None:
        """Rebuild a terminally closed connection without racing concurrent publishers."""
        if self._nc is not None and not self._nc.is_closed:
            return self._nc
        async with self._client_lock:
            if self._nc is None or self._nc.is_closed:
                self._nc = await create_nats_client()
                self._kv = None
        return self._nc

    async def _get_kv(self):
        client = await self._get_client()
        if client is not None and self._kv is None:
            self._kv = await get_or_create_kv_bucket(
                client.jetstream(), f"{nats_settings.scheduler_leader_kv_bucket}_sync"
            )
        return self._kv

    def register_handler(self, topic: MessageTopic, handler: Callable[[dict], Awaitable[None]]):
        self._handlers[topic] = handler

    def register_reconciler(self, topic: MessageTopic, handler: Callable[[dict], Awaitable[None]]):
        """Register a current-database refresh that can repair missed pub/sub messages."""
        self._reconcilers[topic] = handler

    def _queue(self, topic: MessageTopic, data: dict) -> bool:
        queue = self._queues.setdefault(topic, asyncio.Queue(maxsize=TOPIC_QUEUE_LIMIT))
        task = self._topic_tasks.get(topic)
        if task is None or task.done():
            self._topic_tasks[topic] = asyncio.create_task(self._run_topic(topic), name=f"worker-sync-{topic.value}")
        try:
            queue.put_nowait(data)
            return True
        except asyncio.QueueFull:
            # Repair an invalidation backlog from authoritative state instead of
            # silently losing state. These messages are not queued user commands.
            self._dirty.add(topic)
            return False

    def _refresh(self, topic: MessageTopic, revision: str = "") -> None:
        if topic not in self._refresh_pending and self._queue(
            topic, {"_reconcile": True, "_revision": revision, "action": "refresh"}
        ):
            self._refresh_pending.add(topic)

    async def _run_topic(self, topic: MessageTopic) -> None:
        queue = self._queues[topic]
        while True:
            data = await queue.get()
            refresh = bool(data.get("_reconcile"))
            try:
                handler = self._reconcilers.get(topic) if refresh else self._handlers.get(topic)
                if handler is not None:
                    await handler(data)
                    if revision := data.get("_revision"):
                        self._seen[topic] = revision
                    if refresh:
                        self._dirty.discard(topic)
            except Exception:
                self._dirty.add(topic)
                logger.exception("Worker synchronization failed for topic %s", topic.value)
            finally:
                if refresh:
                    self._refresh_pending.discard(topic)
                queue.task_done()

    async def _listen(self):
        """Resubscribe after terminal failures; slow topics never block other topics."""
        while self._running:
            sub = None
            try:
                client = await self._get_client()
                if client is None:
                    return
                sub = await client.subscribe(nats_settings.worker_sync_subject)
                await client.flush(timeout=5)
                self._dirty.update(self._reconcilers)
                self._ready.set()
                async for msg in sub.messages:
                    try:
                        message = NatsMessage.model_validate(json.loads(msg.data))
                    except Exception:
                        logger.warning("Discarding malformed worker synchronization message")
                        continue
                    if message.topic in self._handlers:
                        if message.topic in self._reconcilers and message.topic != MessageTopic.NODE:
                            self._refresh(message.topic, message.data.get("_revision", ""))
                        else:
                            self._queue(message.topic, message.data)
                if self._running:
                    raise RuntimeError("Worker synchronization subscription stopped")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Worker synchronization interrupted; reconnecting", exc_info=True)
                self._dirty.update(self._reconcilers)
                await asyncio.sleep(RECONCILE_INTERVAL)
            finally:
                if sub is not None:
                    with contextlib.suppress(Exception):
                        await sub.unsubscribe()

    async def _reconcile(self, *, force: bool = False, initializing: bool = False) -> None:
        revisions = {}
        try:
            async with asyncio.timeout(RECONCILE_INTERVAL):
                kv = await self._get_kv()
                if kv is not None:
                    for topic in self._reconcilers:
                        try:
                            entry = await kv.get(topic.value)
                        except nats.js.errors.KeyNotFoundError, nats.js.errors.KeyDeletedError:
                            continue
                        revisions[topic] = entry.value.decode()
        except Exception:
            logger.debug("Worker synchronization checkpoints unavailable", exc_info=True)
        for topic in self._reconcilers:
            if initializing and topic == MessageTopic.NODE:
                continue
            revision = revisions.get(topic, "")
            if force or topic in self._dirty or (revision and self._seen.get(topic) != revision):
                self._refresh(topic, revision)

    async def _reconcile_loop(self) -> None:
        last_database_refresh = time.monotonic()
        while self._running:
            await asyncio.sleep(RECONCILE_INTERVAL)
            force = time.monotonic() - last_database_refresh >= DATABASE_RECONCILE_INTERVAL
            await self._reconcile(force=force)
            if force:
                last_database_refresh = time.monotonic()

    async def start(self):
        """Do not advertise readiness before the subscription and initial refresh."""
        if not _router_enabled() or self._running:
            return
        self._running = True
        self._ready.clear()
        self._listener_task = asyncio.create_task(self._listen())
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=30)
            await self._reconcile(force=True, initializing=True)
            # Node initialization has its own startup hook.
            await asyncio.gather(*(q.join() for topic, q in self._queues.items() if topic != MessageTopic.NODE))
            self._reconcile_task = asyncio.create_task(self._reconcile_loop(), name="worker-sync-reconcile")
        except BaseException:
            await self.stop()
            raise

    async def quiesce(self):
        """Stop applying invalidations before local resources begin closing."""
        self._running = False
        tasks = [self._listener_task, self._reconcile_task, *self._topic_tasks.values()]
        for task in tasks:
            if task is not None:
                task.cancel()
        await asyncio.gather(*(task for task in tasks if task is not None), return_exceptions=True)
        self._listener_task = self._reconcile_task = None
        self._topic_tasks.clear()
        self._queues.clear()
        self._refresh_pending.clear()

    async def stop(self):
        await self.quiesce()
        if self._nc is not None:
            await self._nc.close()
        self._nc = self._kv = None

    async def publish(self, topic: MessageTopic, data: dict):
        """Persist the invalidation before broadcasting; surface an unavailable broker."""
        if not _router_enabled():
            return
        revision = uuid4().hex
        kv = await self._get_kv()
        client = await self._get_client()
        if kv is None or client is None:
            raise RuntimeError("NATS synchronization is unavailable")
        await kv.put(topic.value, revision.encode())
        message = NatsMessage(topic=topic, data={**data, "_revision": revision})
        await client.publish(nats_settings.worker_sync_subject, message.model_dump_json().encode())
        await client.flush(timeout=5)


router = NatsMessageRouter()
