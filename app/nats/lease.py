"""Revision-guarded, renewable leases for short shared-state operations."""

import asyncio
import contextlib
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from app.nats.kv_cas import kv_cas_json, kv_get_json


@asynccontextmanager
async def kv_lease(kv, key: str, *, lease_seconds: float = 30.0, acquire_timeout: float = 10.0):
    """Bound the owner's work by the last acknowledged lease renewal."""
    loop = asyncio.get_running_loop()
    token = uuid4().hex
    started = loop.time()
    async with asyncio.timeout(acquire_timeout):
        while True:
            now = time.time()
            doc, revision = await kv_get_json(kv, key)
            if doc is None or float(doc.get("expires_at", 0)) <= now:
                started = loop.time()
                if await kv_cas_json(kv, key, {"token": token, "expires_at": now + lease_seconds}, revision):
                    break
            await asyncio.sleep(0.05)

    async def renew(deadline):
        while True:
            await asyncio.sleep(lease_seconds / 3)
            started = loop.time()
            async with asyncio.timeout_at(deadline.when()):
                doc, revision = await kv_get_json(kv, key)
                if doc is None or doc.get("token") != token:
                    deadline.reschedule(loop.time())
                    return
                payload = {"token": token, "expires_at": time.time() + lease_seconds}
                if not await kv_cas_json(kv, key, payload, revision):
                    deadline.reschedule(loop.time())
                    return
            deadline.reschedule(started + lease_seconds)

    renewal = None
    try:
        async with asyncio.timeout_at(started + lease_seconds) as deadline:
            renewal = asyncio.create_task(renew(deadline))
            yield
    finally:
        if renewal is not None:
            renewal.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await renewal
        # A failed release must not mask cancellation or the original failure.
        with contextlib.suppress(Exception):
            async with asyncio.timeout(5):
                doc, revision = await kv_get_json(kv, key)
                if doc is not None and doc.get("token") == token:
                    await kv.delete(key, last=revision)
