"""Cross-worker node manager sync via NATS worker_sync (MessageTopic.NODE)."""

from __future__ import annotations

import asyncio

from PasarGuardNodeBridge import Health

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


def register_node_sync_handler() -> None:
    router.register_handler(MessageTopic.NODE, handle_node_message)
    router.register_reconciler(MessageTopic.NODE, reconcile_nodes)


async def reconcile_nodes(_: dict | None = None) -> None:
    """Repair missed invalidations without reconnecting unchanged local attachments."""
    from app.operation.node import NodeOperation

    async with GetDB() as db:
        rows, _ = await get_nodes(db, NodeListQuery(), load_usage_logs=False)
    desired = {row.id: row for row in rows if row.status not in (NodeStatus.disabled, NodeStatus.limited)}
    current = dict(await node_manager.get_nodes())
    for node_id in current.keys() - desired.keys():
        await node_manager.remove_node(node_id, remote_stop=False)
    semaphore = asyncio.Semaphore(5)

    async def refresh(row):
        async with semaphore:
            before = await node_manager.get_node(row.id)
            after = await node_manager.update_node(row)
            if after is before:
                if await after.get_health() is Health.NOT_CONNECTED:
                    # A failed first attach must remain retryable even when
                    # neither the database row nor connection signature changes.
                    # Followers only attach to an existing backend; they never Start.
                    await NodeOperation._attach_if_running(after, row.name)
                return
            # Re-read after waiting for a connection lock; deleted/disabled nodes
            # must not be started from an older reconciliation snapshot.
            async with GetDB() as db:
                latest = await get_node_by_id(db, row.id, load_usage_logs=False)
                if latest is None or latest.status in (NodeStatus.disabled, NodeStatus.limited):
                    await node_manager.remove_node(row.id, remote_stop=False)
                    return
                core_id = latest.core_config_id or 1
                cores, users = await NodeOperation._get_core_users_map(db, {core_id}, lazy=True)
                await NodeOperation.connect_node(latest, cores.get(core_id), users.get(core_id, []))

    results = await asyncio.gather(*(refresh(row) for row in desired.values()), return_exceptions=True)
    failures = [result for result in results if isinstance(result, Exception)]
    if failures:
        raise RuntimeError(f"Could not reconcile {len(failures)} local node attachments") from failures[0]
