"""Cross-worker node manager sync via NATS worker_sync (MessageTopic.NODE)."""

from __future__ import annotations

from app.db import GetDB
from app.db.crud.node import get_node_by_id
from app.db.models import NodeStatus
from app.nats.message import MessageTopic
from app.nats.router import router
from app.node import node_manager
from app.node.nats_memory import clear_bridge_memory_for_node
from app.utils.logger import get_logger

logger = get_logger("node-manager-sync")


async def publish_node_sync(action: str, node_id: int) -> None:
    try:
        await router.publish(MessageTopic.NODE, {"action": action, "node_id": node_id})
    except Exception as exc:
        logger.warning("Failed to publish node sync action=%s node_id=%s: %s", action, node_id, exc)


async def handle_node_message(data: dict) -> None:
    action = data.get("action")
    node_id = data.get("node_id")
    if not action or node_id is None:
        return
    node_id = int(node_id)

    if action == "remove":
        await node_manager.remove_node(node_id, remote_stop=False)
        await clear_bridge_memory_for_node(node_id)
        return

    if action == "disconnect":
        await node_manager.remove_node(node_id, remote_stop=False)
        return

    if action == "upsert":
        async with GetDB() as db:
            db_node = await get_node_by_id(db, node_id, load_usage_logs=False)
        if db_node is None:
            return
        await node_manager.update_node(db_node)
        return

    if action == "connect":
        # Quiet attach/start on siblings — originator already wrote DB status / notifications.
        from app.operation.node import NodeOperation

        async with GetDB() as db:
            db_node = await get_node_by_id(db, node_id, load_usage_logs=False)
            if db_node is None or db_node.status in (NodeStatus.disabled, NodeStatus.limited):
                return
            try:
                await node_manager.update_node(db_node)
            except Exception:
                logger.exception("Node sync connect update_node failed for node_id=%s", node_id)
                return
            core_id = db_node.core_config_id or 1
            cores_by_id, users_by_core = await NodeOperation._get_core_users_map(db, {core_id})
            await NodeOperation.connect_node(db_node, cores_by_id.get(core_id), users_by_core.get(core_id, []))
        return

    logger.warning("Unknown node sync action: %s", action)


def register_node_sync_handler() -> None:
    router.register_handler(MessageTopic.NODE, handle_node_message)
