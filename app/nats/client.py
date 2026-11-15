from collections.abc import Awaitable, Callable

import nats
from nats.errors import Error as NatsError
from nats.js.client import JetStreamContext
from nats.js.kv import KeyValue

from app.utils.logger import get_logger

from . import get_nats_config, is_nats_enabled

logger = get_logger("nats-client")


async def create_nats_client(*, reconnected_cb: Callable[[], Awaitable[None]] | None = None) -> nats.NATS | None:
    """Create a new NATS connection."""
    if not is_nats_enabled():
        return None
    cfg = get_nats_config()
    nc = nats.NATS()
    connected = False

    async def _error_cb(exc: Exception) -> None:
        # While the server is down every reconnect attempt of every connection fails;
        # one traceback per attempt flooded the log, so those attempts are logged at debug.
        # A refused login or handshake and a failing first connect stay visible.
        is_network_error = isinstance(exc, OSError | TimeoutError) and not isinstance(exc, NatsError)
        if connected and is_network_error and (nc.is_reconnecting or nc.is_connecting):
            logger.debug(f"NATS reconnect attempt failed: {exc!r}")
        else:
            logger.warning(f"NATS error: {exc!r}")

    async def _disconnected_cb() -> None:
        if not nc.is_closed:
            logger.warning("NATS connection lost, reconnecting")

    async def _reconnected_cb() -> None:
        logger.info("NATS connection restored")
        if reconnected_cb is not None:
            await reconnected_cb()

    # The first connect keeps the default budget: nats-py applies max_reconnect_attempts to it
    # too, and -1 would make an unreachable server or a refused login hang the caller forever.
    await nc.connect(
        cfg["url"],
        error_cb=_error_cb,
        disconnected_cb=_disconnected_cb,
        reconnected_cb=_reconnected_cb,
    )
    connected = True
    # Once connected, reconnect without a limit (nats-py reads the option on every attempt):
    # after the default budget ran out the client closed for good until a restart.
    nc.options["max_reconnect_attempts"] = -1
    return nc


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
