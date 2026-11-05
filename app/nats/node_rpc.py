import asyncio
import json

import nats.errors

from app.nats.rpc_client import NatsRpcClient
from app.utils.logger import get_logger
from config import nats_settings

logger = get_logger("node-nats")

CONTROL_NODE_COMMANDS = frozenset(
    {"update_node", "remove_node", "connect_node", "connect_nodes_bulk", "disconnect_node", "sync_node_users"}
)
# Start and full synchronization can take as long as a maintenance RPC.
NODE_CONTROL_TIMEOUT = 340.0


def node_control_subject() -> str:
    """Keep acknowledged control requests separate from legacy broadcast commands."""
    return f"{nats_settings.node_command_subject}.control"


def encode_node_command(action: str, payload: dict) -> bytes:
    message = {"action": action, "payload": payload}
    return json.dumps(message, separators=(",", ":")).encode()


class NodeNatsClient(NatsRpcClient):
    def __init__(self):
        super().__init__(nats_settings.node_rpc_subject, nats_settings.node_rpc_timeout, error_message="Node RPC error")

    async def publish(self, action: str, payload: dict):
        """Wait for control commands to finish; retain the user-update transport."""
        if action in CONTROL_NODE_COMMANDS:
            try:
                timeout = max(NODE_CONTROL_TIMEOUT, nats_settings.node_rpc_timeout)
                # The budget includes connection establishment, not just the reply.
                async with asyncio.timeout(timeout):
                    return await self.request(action, payload, timeout=timeout, subject=node_control_subject())
            except (nats.errors.Error, OSError) as exc:
                # The built-in TimeoutError raised by asyncio.timeout is an OSError.
                # A timed-out request may already have reached the node. Do not
                # automatically repeat a force restart or a full user flush.
                error = RuntimeError(
                    f"Node command {action!r} was not confirmed; check the node status before retrying"
                )
                error.code = 503
                raise error from exc
        client = await self._get_client()
        if not client:
            return
        try:
            await client.publish(nats_settings.node_command_subject, encode_node_command(action, payload))
        except Exception as exc:
            logger.warning(f"Failed to publish node command: {exc}")


node_nats_client = NodeNatsClient()
