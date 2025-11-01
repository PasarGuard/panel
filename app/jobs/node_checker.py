import asyncio

from PasarGuardNodeBridge import NodeAPIError, PasarGuardNode, Health

from app import on_shutdown, on_startup, scheduler
from app.db import GetDB
from app.db.models import Node, NodeStatus
from app.db.crud.node import get_nodes
from app.node import node_manager
from app.utils.logger import get_logger
from app.operation.node import NodeOperation
from app.operation import OperatorType

from config import JOB_CORE_HEALTH_CHECK_INTERVAL


node_operator = NodeOperation(operator_type=OperatorType.SYSTEM)
logger = get_logger("node-checker")


async def verify_node_backend_health(node: PasarGuardNode, node_name: str) -> Health:
    """
    Verify node health by checking backend stats.
    Returns updated health status.
    """
    current_health = await node.get_health()

    # Skip nodes that are not connected or invalid
    if current_health in (Health.NOT_CONNECTED, Health.INVALID):
        return current_health

    try:
        await asyncio.wait_for(node.get_backend_stats(), timeout=10)
        if current_health != Health.HEALTHY:
            await node.set_health(Health.HEALTHY)
            logger.info(f"[{node_name}] Node health is HEALTHY")
        return Health.HEALTHY
    except Exception as e:
        error_type = type(e).__name__
        logger.error(f"[{node_name}] Health check failed, setting health to BROKEN | Error: {error_type} - {str(e)}")
        try:
            await node.set_health(Health.BROKEN)
            return Health.BROKEN
        except Exception as e_set_health:
            error_type_set = type(e_set_health).__name__
            logger.error(
                f"[{node_name}] Failed to set health to BROKEN | Error: {error_type_set} - {str(e_set_health)}"
            )
            return current_health


async def update_node_connection_status(node_id: int, node: PasarGuardNode):
    """
    Update node connection status by getting backend stats and version info.
    """
    try:
        await node.get_backend_stats(timeout=8)
        await node_operator.update_node_status(
            node_id, NodeStatus.connected, await node.core_version(), await node.node_version()
        )
    except NodeAPIError as e:
        if e.code > -3:
            await node_operator.update_node_status(node_id, NodeStatus.error, err=e.detail)
        if e.code > 0:
            await node_operator.connect_node(node_id=node_id)


async def process_node_health_check(db_node: Node, node: PasarGuardNode):
    """
    Process health check for a single node:
    1. Check if node requires hard reset
    2. Verify backend health
    3. Compare with database status
    4. Update status if needed
    """
    if node is None:
        return

    if node.requires_hard_reset():
        await node_operator.connect_node(db_node.id)
        return

    try:
        health = await asyncio.wait_for(verify_node_backend_health(node, db_node.name), timeout=15)
    except asyncio.TimeoutError:
        await node_operator.update_node_status(db_node.id, NodeStatus.error, err="Health check timeout")
        return
    except NodeAPIError:
        await node_operator.update_node_status(db_node.id, NodeStatus.error, err="Get health failed")
        return

    # Skip nodes that are already healthy and connected
    if health == Health.HEALTHY and db_node.status == NodeStatus.connected:
        return

    # Update status for recovering nodes
    if db_node.status in (NodeStatus.connecting, NodeStatus.error) and health == Health.HEALTHY:
        await node_operator.update_node_status(
            db_node.id,
            NodeStatus.connected,
            core_version=await node.core_version(),
            node_version=await node.node_version(),
        )
        return

    # For all other cases, update connection status
    await update_node_connection_status(db_node.id, node)


async def node_health_check():
    """
    Cron job that checks health of all enabled nodes.
    """
    async with GetDB() as db:
        db_nodes = await get_nodes(db=db, enabled=True)
        dict_nodes = await node_manager.get_nodes()

        check_tasks = [process_node_health_check(db_node, dict_nodes.get(db_node.id)) for db_node in db_nodes]
        await asyncio.gather(*check_tasks, return_exceptions=True)


@on_startup
async def initialize_nodes():
    logger.info("Starting nodes' cores...")

    async with GetDB() as db:
        db_nodes = await get_nodes(db=db, enabled=True)

        # Semaphore to limit concurrent node startups to 3 at a time
        semaphore = asyncio.Semaphore(3)

        async def start_node(node: Node):
            try:
                await node_manager.update_node(node)
            except NodeAPIError as e:
                await node_operator.update_node_status(node.id, NodeStatus.error, err=e.detail)
                return

            await node_operator.connect_node(node_id=node.id)

        async def start_node_with_limit(node: Node):
            async with semaphore:
                await start_node(node)

        if not db_nodes:
            logger.warning("Attention: You have no node, you need to have at least one node")
        else:
            start_tasks = [start_node_with_limit(db_node) for db_node in db_nodes]
            await asyncio.gather(*start_tasks)
            logger.info("All nodes' cores have been started.")

    scheduler.add_job(
        node_health_check, "interval", seconds=JOB_CORE_HEALTH_CHECK_INTERVAL, coalesce=True, max_instances=1
    )


@on_shutdown
async def shutdown_nodes():
    logger.info("Stopping nodes' cores...")

    nodes: dict[int, PasarGuardNode] = await node_manager.get_nodes()

    stop_tasks = [node.stop() for node in nodes.values()]

    # Run all tasks concurrently and wait for them to complete
    await asyncio.gather(*stop_tasks, return_exceptions=True)

    logger.info("All nodes' cores have been stopped.")
