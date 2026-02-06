import json

from app.nats.rpc_client import NatsRpcClient
from app.utils.logger import get_logger
from config import NATS_NODE_COMMAND_SUBJECT, NATS_NODE_RPC_SUBJECT, NATS_NODE_RPC_TIMEOUT

logger = get_logger("node-nats")


class NodeNatsClient(NatsRpcClient):
    def __init__(self):
        super().__init__(NATS_NODE_RPC_SUBJECT, NATS_NODE_RPC_TIMEOUT, error_message="Node RPC error")

    async def publish(self, action: str, payload: dict):
        client = await self._get_client()
        if not client:
            return
        message = {"action": action, "payload": payload}
        try:
            await client.publish(NATS_NODE_COMMAND_SUBJECT, json.dumps(message).encode())
        except Exception as exc:
            logger.warning(f"Failed to publish node command: {exc}")


node_nats_client = NodeNatsClient()
