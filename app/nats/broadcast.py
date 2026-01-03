import asyncio
import base64
import json
import os
import pickle
from collections import deque
from typing import Any, Awaitable, Callable

from nats.aio.msg import Msg
from nats.aio.subscription import Subscription

from app.nats import is_nats_enabled
from app.nats.client import NatsClient
from app.nats.contracts import (
    BroadcastEnvelope,
    BroadcastEvent,
    PANEL_BROADCAST_OBJECT_CHANGED_SUBJECT,
    PANEL_BROADCAST_STREAM,
    PANEL_BROADCAST_SUBJECT,
)
from app.utils.logger import get_logger


BroadcastHandler = Callable[[BroadcastEnvelope, Any], Awaitable[None]]

logger = get_logger("nats-broadcast")


class BroadcastClient:
    """
    Broadcast publisher/subscriber for cache/state invalidations.

    Publishes pickled payloads in a JSON envelope; all consumers (including the
    publisher) process updates through the registered handlers.
    """

    def __init__(
        self,
        *,
        subject: str = PANEL_BROADCAST_SUBJECT,
        stream_name: str = PANEL_BROADCAST_STREAM,
        publisher_id: str | None = None,
        durable: str | None = None,
        dedupe_size: int = 2048,
    ):
        self._subject = subject
        self._stream_name = stream_name
        self._publisher_id = publisher_id or os.getenv("SERVICE_ID") or os.getenv("HOSTNAME") or "panel"
        self._durable = durable
        self._nats = NatsClient()
        self._handlers: dict[str, BroadcastHandler] = {}
        self._task: asyncio.Task | None = None
        self._sub: Subscription | None = None
        self._running = False

        self._dedupe_ids: deque[str] = deque(maxlen=dedupe_size)
        self._dedupe_set: set[str] = set()

    def register_handler(self, object_type: str, handler: BroadcastHandler):
        """Register a handler for an object type. Use '*' as a catch-all."""
        self._handlers[object_type] = handler
        logger.debug("Registered broadcast handler for %s", object_type)

    async def start(self):
        """Start listening for broadcast messages."""
        if self._running or not is_nats_enabled():
            return

        nc = await self._nats.connect()
        if not nc:
            logger.warning("BroadcastClient could not connect to NATS; broadcasts disabled.")
            return

        await self._nats.ensure_stream(self._stream_name, [self._subject])

        if self._nats.js:
            self._sub = await self._nats.js.subscribe(
                self._subject,
                durable=self._durable,
                manual_ack=True,
            )
        else:
            self._sub = await self._nats.nc.subscribe(self._subject)

        self._running = True
        self._task = asyncio.create_task(self._listener())
        logger.info("BroadcastClient started on %s", self._subject)

    async def stop(self):
        """Stop listening and close NATS connection."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._nats.close()
        self._sub = None
        logger.info("BroadcastClient stopped")

    async def publish_object_changed(
        self,
        obj: Any,
        *,
        object_type: str,
        object_id: Any,
        event_type: str = BroadcastEvent.OBJECT_CHANGED.value,
        schema_version: int = 1,
        object_version: int | None = None,
    ) -> BroadcastEnvelope | None:
        """
        Publish an object_changed broadcast. Returns the envelope on success.
        """
        if not is_nats_enabled():
            logger.debug("NATS disabled; skipping broadcast for %s:%s", object_type, object_id)
            return None

        nc = await self._nats.connect()
        if not nc:
            logger.warning("Cannot broadcast object change; NATS connection unavailable.")
            return None

        await self._nats.ensure_stream(self._stream_name, [self._subject])

        try:
            payload_bytes = pickle.dumps(obj)
            payload = base64.b64encode(payload_bytes).decode()
        except Exception as exc:
            logger.error("Failed to pickle %s:%s for broadcast: %s", object_type, object_id, exc)
            return None

        envelope = BroadcastEnvelope(
            event_type=event_type,
            object_type=object_type,
            object_id=str(object_id),
            schema_version=schema_version,
            publisher_id=self._publisher_id,
            payload_bytes=payload,
            object_version=object_version,
        )

        data = json.dumps(envelope.model_dump(mode="json"), default=str).encode()

        try:
            await self._nats.publish(PANEL_BROADCAST_OBJECT_CHANGED_SUBJECT, data, msg_id=envelope.msg_id)
        except Exception as exc:
            logger.error("Failed to publish broadcast for %s:%s: %s", object_type, object_id, exc)
            return None

        return envelope

    def _seen(self, event_id: str) -> bool:
        if event_id in self._dedupe_set:
            return True
        if len(self._dedupe_ids) == self._dedupe_ids.maxlen:
            oldest = self._dedupe_ids.popleft()
            self._dedupe_set.discard(oldest)
        self._dedupe_ids.append(event_id)
        self._dedupe_set.add(event_id)
        return False

    async def _listener(self):
        if not self._sub:
            return

        try:
            async for msg in self._sub.messages:
                await self._handle_message(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Broadcast listener stopped: %s", exc, exc_info=True)
            self._running = False

    async def _handle_message(self, msg: Msg):
        try:
            payload = json.loads(msg.data.decode())
            envelope = BroadcastEnvelope.model_validate(payload)
        except Exception as exc:
            logger.warning("Invalid broadcast message: %s", exc)
            if hasattr(msg, "ack"):
                try:
                    await msg.ack()
                except Exception:
                    pass
            return

        if self._seen(envelope.event_id):
            if hasattr(msg, "ack"):
                await msg.ack()
            return

        handler = self._handlers.get(envelope.object_type) or self._handlers.get("*")
        if not handler:
            logger.debug("No broadcast handler for %s", envelope.object_type)
            if hasattr(msg, "ack"):
                await msg.ack()
            return

        try:
            raw_bytes = base64.b64decode(envelope.payload_bytes)
            obj = pickle.loads(raw_bytes)
        except Exception as exc:
            logger.error("Failed to decode broadcast payload for %s: %s", envelope.object_type, exc)
            if hasattr(msg, "ack"):
                await msg.ack()
            return

        try:
            await handler(envelope, obj)
        except Exception as exc:
            logger.error("Broadcast handler error for %s: %s", envelope.object_type, exc, exc_info=True)
        finally:
            if hasattr(msg, "ack"):
                try:
                    await msg.ack()
                except Exception:
                    pass


broadcast_client = BroadcastClient()


async def start_broadcast_client():
    await broadcast_client.start()


async def stop_broadcast_client():
    await broadcast_client.stop()
