import asyncio
import json
from uuid import uuid4

import nats.errors
from nats.js.errors import APIError

from app.nats.node_commands import USER_COMMANDS, ensure_user_command_stream, user_command_subject
from app.nats.rpc_client import NatsRpcClient
from app.utils.logger import get_logger
from config import nats_settings

logger = get_logger("node-nats")


def encode_node_command(action: str, payload: dict) -> bytes:
    message = {"action": action, "payload": payload}
    return json.dumps(message, separators=(",", ":")).encode()


class NodeNatsClient(NatsRpcClient):
    def __init__(self):
        super().__init__(nats_settings.node_rpc_subject, nats_settings.node_rpc_timeout, error_message="Node RPC error")
        self._user_stream_connection = None

    async def _publish_user_command(self, message: bytes):
        message_id = uuid4().hex
        delay = 0.5
        while True:
            try:
                client = await self._get_client()
                if client is None:
                    raise RuntimeError("NATS is not available for node user commands")
                js = client.jetstream()
                if self._user_stream_connection is not client:
                    await ensure_user_command_stream(js)
                    self._user_stream_connection = client
                # Reuse the id when an acknowledgement is lost after the server stores it.
                await js.publish(user_command_subject(), message, headers={"Nats-Msg-Id": message_id})
                return
            except nats.errors.Error as exc:
                if isinstance(exc, (nats.errors.MaxPayloadError, nats.errors.BadSubjectError)):
                    raise
                if isinstance(exc, APIError) and exc.code is not None and 400 <= exc.code < 500:
                    raise
                self._user_stream_connection = None
                logger.warning("Node user command was not acknowledged; retrying in %.1fs: %s", delay, exc)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    async def publish(self, action: str, payload: dict):
        if action in USER_COMMANDS:
            await self._publish_user_command(encode_node_command(action, payload))
            return
        client = await self._get_client()
        if not client:
            return
        try:
            await client.publish(nats_settings.node_command_subject, encode_node_command(action, payload))
        except Exception as exc:
            logger.warning(f"Failed to publish node command: {exc}")


node_nats_client = NodeNatsClient()
