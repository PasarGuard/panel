"""Cross-worker node manager sync via NATS worker_sync (MessageTopic.NODE)."""

from __future__ import annotations

from app.db import GetDB
from app.db.crud.node import get_node_by_id
from app.db.models import NodeStatus
from app.nats.message import MessageTopic
from app.nats.router import router
from app.node import node_manager
from app.node.nats_memory import WORKER_ID
from app.utils.logger import get_logger

logger = get_logger("node-manager-sync")


async def publish_node_sync(action: str, node_id: int, bridge_id: str | None = None) -> None:
    try:
        data = {"action": action, "node_id": node_id, "origin": WORKER_ID}
        if bridge_id is not None:
            data["bridge_id"] = bridge_id
        await router.publish(
            MessageTopic.NODE,
            data,
        )
    except Exception as exc:
        logger.warning("Failed to publish node sync action=%s node_id=%s: %s", action, node_id, exc)


async def handle_node_message(data: dict) -> None:
    if data.get("origin") == WORKER_ID:
        return

    action = data.get("action")
    node_id = data.get("node_id")
    if not action or node_id is None:
        return
    node_id = int(node_id)
    announced_bridge_id = data.get("bridge_id")

    if action == "remove":
        if announced_bridge_id is None:
            logger.warning("Ignoring unsafe legacy node remove without bridge_id node_id=%s", node_id)
            return
        remove_kwargs = {"remote_stop": False, "permanent_delete": True}
        remove_kwargs["expected_bridge_namespace"] = str(announced_bridge_id)
        await node_manager.remove_node(node_id, **remove_kwargs)
        return

    if action == "disconnect":
        remove_kwargs = {"remote_stop": False}
        if announced_bridge_id is not None:
            remove_kwargs["expected_bridge_namespace"] = str(announced_bridge_id)
        await node_manager.remove_node(node_id, **remove_kwargs)
        return

    if action == "upsert":
        async with GetDB() as db:
            db_node = await get_node_by_id(db, node_id, load_usage_logs=False)
        if db_node is None:
            return
        if announced_bridge_id is not None and str(db_node.bridge_id) != str(announced_bridge_id):
            logger.warning("Ignoring stale node sync action=%s node_id=%s", action, node_id)
            return
        if not await node_manager.runtime_matches(db_node):
            await node_manager.update_node(db_node)
        return

    if action == "connect":
        # Quiet attach/start on siblings — originator already wrote DB status / notifications.
        from app.operation.node import NodeOperation

        async with GetDB() as db:
            db_node = await get_node_by_id(db, node_id, load_usage_logs=False)
            if db_node is None or db_node.status in (NodeStatus.disabled, NodeStatus.limited):
                return
            if announced_bridge_id is not None and str(db_node.bridge_id) != str(announced_bridge_id):
                logger.warning("Ignoring stale node connect node_id=%s", node_id)
                return
            # Match the local startup ordering. Register this worker's runtime
            # before locking the authoritative user snapshot, then keep those
            # row locks until the epoch-fenced full apply completes. A delete
            # either sees this runtime in topology or commits before snapshot.
            try:
                if not await node_manager.runtime_matches(db_node):
                    await node_manager.update_node(db_node)
            except Exception:
                logger.exception("Node sync connect runtime registration failed for node_id=%s", node_id)
                return
            core_id = db_node.core_config_id or 1
            cores_by_id, users_by_core, authoritative_user_keys = await NodeOperation._get_core_users_map(
                db, {core_id}
            )
            core = cores_by_id.get(core_id)
            users = users_by_core.get(core_id, [])
            await NodeOperation.connect_node(db_node, core, users, authoritative_user_keys)
        return

    logger.warning("Unknown node sync action: %s", action)


def register_node_sync_handler() -> None:
    router.register_handler(MessageTopic.NODE, handle_node_message)
