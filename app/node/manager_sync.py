"""Cross-worker node manager sync via NATS worker_sync (MessageTopic.NODE)."""

from __future__ import annotations

from app.db import GetDB
from app.db.crud.node import get_node_by_id, get_nodes
from app.db.models import NodeStatus
from app.models.node import NodeListQuery
from app.nats.message import MessageTopic
from app.nats.router import router
from app.node import node_manager
from app.node.nats_memory import WORKER_ID, clear_bridge_memory_for_node
from app.utils.logger import get_logger

logger = get_logger("node-manager-sync")


async def publish_node_sync(action: str, node_id: int) -> None:
    try:
        await router.publish(
            MessageTopic.NODE,
            {"action": action, "node_id": node_id, "origin": WORKER_ID},
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
            core_id = db_node.core_config_id or 1
            cores_by_id, users_by_core = await NodeOperation._get_core_users_map(db, {core_id}, lazy=True)
            core = cores_by_id.get(core_id)
            users = users_by_core.get(core_id, [])

            try:
                await node_manager.update_node(db_node)
            except Exception:
                logger.exception("Node sync connect update_node failed for node_id=%s", node_id)
                return
            await NodeOperation.connect_node(db_node, core, users)
        return

    logger.warning("Unknown node sync action: %s", action)


async def resync_nodes() -> None:
    """Attach, update and drop nodes to match the database after node sync messages were lost."""
    from app.jobs.node_checker import ACTIVE_NODE_STATUSES

    # Taken before the database is read: a node attached on this worker in between is then active in
    # the read and kept, instead of being dropped as missing from it
    attached = set((await node_manager.get_nodes()).keys())
    async with GetDB() as db:
        db_nodes, _ = await get_nodes(db=db, query=NodeListQuery(status=ACTIVE_NODE_STATUSES), load_usage_logs=False)
    active = {db_node.id for db_node in db_nodes}

    for node_id in attached - active:
        try:
            # Same as a missed "remove"/"disconnect": the originator already stopped the node
            await node_manager.remove_node(node_id, remote_stop=False)
        except Exception:
            logger.exception("Node resync failed to drop node_id=%s", node_id)
    for node_id in active:
        try:
            if node_id in attached:
                # Same as a missed "upsert", a no-op while the connection settings are unchanged. Read
                # again: a node removed or disabled since the list was read must not be recreated.
                async with GetDB() as db:
                    db_node = await get_node_by_id(db, node_id, load_usage_logs=False)
                if db_node is None or db_node.status not in ACTIVE_NODE_STATUSES:
                    continue
                await node_manager.update_node(db_node)
            else:
                await handle_node_message({"action": "connect", "node_id": node_id})
        except Exception:
            logger.exception("Node resync failed for node_id=%s", node_id)


def register_node_sync_handler() -> None:
    router.register_handler(MessageTopic.NODE, handle_node_message)
    router.register_resync_handler(MessageTopic.NODE, resync_nodes)
