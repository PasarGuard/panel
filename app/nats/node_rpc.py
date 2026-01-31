import asyncio
import json

import nats

from app.nats import is_nats_enabled
from app.nats.client import create_nats_client
from app.utils.logger import get_logger
from config import NATS_NODE_COMMAND_SUBJECT, NATS_NODE_RPC_SUBJECT, NATS_NODE_RPC_TIMEOUT

logger = get_logger("node-nats")


class NodeNatsClient:
    def __init__(self):
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

    async def publish(self, action: str, payload: dict):
        client = await self._get_client()
        if not client:
            return
        message = {"action": action, "payload": payload}
        try:
            await client.publish(NATS_NODE_COMMAND_SUBJECT, json.dumps(message).encode())
        except Exception as exc:
            logger.warning(f"Failed to publish node command: {exc}")

    async def request(self, action: str, payload: dict, timeout: float | None = None) -> dict:
        client = await self._get_client()
        if not client:
            raise RuntimeError("NATS is not available")

        message = {"action": action, "payload": payload}
        timeout = timeout if timeout is not None else NATS_NODE_RPC_TIMEOUT
        reply = await client.request(NATS_NODE_RPC_SUBJECT, json.dumps(message).encode(), timeout=timeout)
        response = json.loads(reply.data.decode())

        if not response.get("ok", False):
            error_msg = response.get("error", "Node RPC error")
            error_code = response.get("code", 500)
            exc = RuntimeError(error_msg)
            exc.code = error_code  # Attach code to exception for caller to handle
            raise exc

        return response.get("data")

    async def close(self):
        if self._nc and not self._nc.is_closed:
            await self._nc.close()
        self._nc = None


node_nats_client = NodeNatsClient()
