import asyncio
import contextlib

import nats
from nats.js.client import JetStreamContext
from nats.js.kv import KeyValue

from . import get_nats_config, is_nats_enabled


async def create_nats_client(**options) -> nats.NATS | None:
    """Reconnect for the lifetime of the service instead of abandoning its KV handles."""
    if not is_nats_enabled():
        return None
    cfg = get_nats_config()
    options.setdefault("max_reconnect_attempts", -1)
    nc = nats.NATS()
    try:
        async with asyncio.timeout(30):
            await nc.connect(cfg["url"], **options)
        return nc
    except BaseException:
        with contextlib.suppress(Exception):
            await nc.close()
        raise


async def get_jetstream_context(nc: nats.NATS) -> JetStreamContext:
    """Get JetStream context from NATS connection. JetStream is always enabled."""
    return nc.jetstream()


async def get_or_create_kv_bucket(js: JetStreamContext, bucket_name: str, **options) -> KeyValue | None:
    """Get or create a JetStream KV bucket."""
    try:
        return await js.create_key_value(bucket=bucket_name, **options)
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

    try:
        js = await get_jetstream_context(nc)
        kv = await get_or_create_kv_bucket(js, bucket_name)
        return nc, js, kv
    except BaseException:
        with contextlib.suppress(Exception):
            await nc.close()
        raise
