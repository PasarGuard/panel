import nats
from nats.js.api import DiscardPolicy, StreamConfig
from nats.js.client import JetStreamContext
from nats.js.errors import BadRequestError
from nats.js.kv import KeyValue

from . import get_nats_config, is_nats_enabled
from app.utils.logger import get_logger


logger = get_logger("nats-client")


async def create_nats_client() -> nats.NATS | None:
    """Create a new NATS connection."""
    if not is_nats_enabled():
        return None
    cfg = get_nats_config()
    return await nats.connect(cfg["url"])


async def get_jetstream_context(nc: nats.NATS) -> JetStreamContext:
    """Get JetStream context from NATS connection. JetStream is always enabled."""
    return nc.jetstream()


async def get_or_create_kv_bucket(js: JetStreamContext, bucket_name: str) -> KeyValue | None:
    """Get or create a JetStream KV bucket."""
    try:
        return await js.create_key_value(bucket=bucket_name)
    except Exception:
        # Bucket already exists
        return await js.key_value(bucket=bucket_name)


async def setup_nats_kv(bucket_name: str) -> tuple[nats.NATS | None, JetStreamContext | None, KeyValue | None]:
    """
    Set up NATS client, JetStream context, and KV bucket in one call.
    Returns (nc, js, kv) tuple. All will be None if NATS is not enabled.
    """
    if not is_nats_enabled():
        return None, None, None

    nc = await create_nats_client()
    if not nc:
        return None, None, None

    js = await get_jetstream_context(nc)
    kv = await get_or_create_kv_bucket(js, bucket_name)

    return nc, js, kv


class NatsClient:
    """Managed NATS client with optional JetStream helper utilities."""

    def __init__(self):
        self._nc: nats.NATS | None = None
        self._js: JetStreamContext | None = None

    @property
    def nc(self) -> nats.NATS | None:
        return self._nc

    @property
    def js(self) -> JetStreamContext | None:
        return self._js

    async def connect(self) -> nats.NATS | None:
        """Establish connection and JetStream context (if enabled)."""
        if self._nc:
            return self._nc

        self._nc = await create_nats_client()
        if not self._nc:
            return None

        try:
            self._js = await get_jetstream_context(self._nc)
        except Exception as exc:
            logger.warning("JetStream context unavailable: %s", exc)
            self._js = None

        return self._nc

    async def ensure_stream(self, stream_name: str, subjects: list[str]):
        """Create a JetStream stream if it does not already exist."""
        if not self._js:
            return

        try:
            await self._js.add_stream(
                StreamConfig(
                    name=stream_name,
                    subjects=subjects,
                    discard=DiscardPolicy.Old,
                )
            )
        except BadRequestError:
            # Stream already exists
            pass
        except Exception as exc:
            logger.warning("Failed to ensure JetStream stream %s: %s", stream_name, exc)

    async def publish(self, subject: str, payload: bytes, *, msg_id: str | None = None):
        """Publish with optional JetStream message id for deduplication."""
        if not self._nc:
            await self.connect()
        if not self._nc:
            return

        if self._js:
            await self._js.publish(subject, payload, msg_id=msg_id)
        else:
            await self._nc.publish(subject, payload, headers={"Nats-Msg-Id": msg_id} if msg_id else None)

    async def subscribe(self, subject: str, **kwargs):
        """Subscribe to a subject. If JetStream is available, use it; otherwise regular subscribe."""
        if not self._nc:
            await self.connect()
        if not self._nc:
            return None

        if self._js:
            return await self._js.subscribe(subject, **kwargs)
        return await self._nc.subscribe(subject, **kwargs)

    async def close(self):
        if self._nc:
            await self._nc.close()
        self._nc = None
        self._js = None


__all__ = [
    "NatsClient",
    "create_nats_client",
    "get_jetstream_context",
    "get_or_create_kv_bucket",
    "setup_nats_kv",
]
