import json

from app.nats.rpc_client import NatsRpcClient
from app.utils.logger import get_logger
from config import nats_settings

logger = get_logger("node-nats")


class NodeNatsClient(NatsRpcClient):
    def __init__(self):
        super().__init__(nats_settings.node_rpc_subject, nats_settings.node_rpc_timeout, error_message="Node RPC error")

    async def publish(self, action: str, payload: dict):
        client = await self._get_client()
        if not client:
            return
        message = {"action": action, "payload": payload}
        try:
            await client.publish(nats_settings.node_command_subject, json.dumps(message).encode())
        except Exception as exc:
            logger.warning(f"Failed to publish node command: {exc}")


node_nats_client = NodeNatsClient()
