import json
from typing import Any

import nats
from nats.js.api import DiscardPolicy, StreamConfig
from nats.js.errors import BadRequestError

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client, get_jetstream_context
from app.nats.contracts import JobMessage
from app.utils.logger import get_logger

logger = get_logger("nats-publisher")


class NatsPublisher:
    """
    Lightweight NATS wrapper for publish, request/reply, and JetStream enqueue.

    This client maintains a single connection and (optionally) a JetStream stream
    for durable job delivery.
    """

    def __init__(self, stream_name: str = "PANEL_JOBS", stream_subjects: tuple[str, ...] = ("panel.jobs.>",)):
        self._nc: nats.NATS | None = None
        self._js = None
        self._stream_name = stream_name
        self._stream_subjects = stream_subjects
        self._stream_ready = False

    async def _ensure_connection(self):
        if not is_nats_enabled():
            raise RuntimeError("NATS is disabled; enable NATS_ENABLED to publish jobs.")

        if self._nc is None:
            self._nc = await create_nats_client()
            if not self._nc:
                raise RuntimeError("Failed to connect to NATS.")

        if self._js is None:
            self._js = await get_jetstream_context(self._nc)

    async def _ensure_stream(self):
        if self._stream_ready or not self._js or not self._stream_name:
            return

        try:
            await self._js.add_stream(
                StreamConfig(
                    name=self._stream_name,
                    subjects=list(self._stream_subjects),
                    discard=DiscardPolicy.Old,
                )
            )
        except BadRequestError:
            # Stream already exists
            pass
        except Exception as exc:  # pragma: no cover - defensive log
            logger.warning("Failed to ensure JetStream stream: %s", exc)
        else:
            logger.debug("JetStream stream %s ensured with subjects %s", self._stream_name, self._stream_subjects)

        self._stream_ready = True

    @staticmethod
    def _encode(message: Any) -> bytes:
        if isinstance(message, JobMessage):
            payload = message.model_dump(mode="json")
        elif hasattr(message, "model_dump"):
            payload = message.model_dump(mode="json")
        elif isinstance(message, dict):
            payload = message
        else:
            raise TypeError("Message must be JobMessage, pydantic model, or dict.")
        return json.dumps(payload, default=str).encode()

    async def publish(self, subject: str, message: Any, *, idempotency_key: str | None = None):
        """Fire-and-forget publish (non-JetStream)."""
        await self._ensure_connection()
        data = self._encode(message)
        headers = {"Nats-Msg-Id": idempotency_key} if idempotency_key else None
        await self._nc.publish(subject, data, headers=headers)

    async def request(self, subject: str, message: Any, *, timeout: float = 2.0):
        """Request/reply helper for synchronous flows."""
        await self._ensure_connection()
        data = self._encode(message)
        response = await self._nc.request(subject, data, timeout=timeout)
        return response

    async def enqueue(
        self,
        subject: str,
        message: Any,
        *,
        idempotency_key: str | None = None,
        timeout: float | None = None,
    ):
        """
        Enqueue a message via JetStream with optional de-duplication.

        Uses the publisher's configured stream/subjects.
        """
        await self._ensure_connection()
        await self._ensure_stream()

        if not self._js:
            raise RuntimeError("JetStream is not available on the current NATS connection.")

        data = self._encode(message)
        await self._js.publish(subject, data, timeout=timeout, msg_id=idempotency_key)

    async def close(self):
        if self._nc:
            await self._nc.close()
            self._nc = None
            self._js = None
            self._stream_ready = False


__all__ = ["NatsPublisher"]
