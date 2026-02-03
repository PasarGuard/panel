import asyncio
import json

import nats

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client


class NatsRpcClient:
    def __init__(self, subject: str, timeout: float, error_message: str = "RPC error"):
        self._subject = subject
        self._timeout = timeout
        self._error_message = error_message
        self._nc: nats.NATS | None = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> nats.NATS | None:
        if not is_nats_enabled():
            return None
        if self._nc and not self._nc.is_closed:
            return self._nc
        async with self._lock:
            if self._nc and not self._nc.is_closed:
                return self._nc
            self._nc = await create_nats_client()
            return self._nc

    async def get_client(self) -> nats.NATS | None:
        return await self._get_client()

    async def request(self, action: str, payload: dict, timeout: float | None = None) -> dict:
        client = await self._get_client()
        if not client:
            raise RuntimeError("NATS is not available")

        message = {"action": action, "payload": payload}
        timeout = timeout if timeout is not None else self._timeout
        reply = await client.request(self._subject, json.dumps(message).encode(), timeout=timeout)
        response = json.loads(reply.data.decode())

        if not response.get("ok", False):
            error_msg = response.get("error", self._error_message)
            error_code = response.get("code", 500)
            exc = RuntimeError(error_msg)
            exc.code = error_code
            raise exc

        return response.get("data")

    async def close(self):
        if self._nc and not self._nc.is_closed:
            await self._nc.close()
        self._nc = None
