import asyncio

from PasarGuardNodeBridge import NodeAPIError, PasarGuardNode, Health

from app import on_shutdown, on_startup, scheduler, notification
from app.db import GetDB
from app.db.models import Node, NodeStatus
from app.models.node import NodeNotification
from app.node import node_manager
from app.utils.logger import get_logger
from app.operation.node import NodeOperation
from app.operation import OperatorType
from app.db.crud.node import get_limited_nodes, get_nodes

from config import JOB_CORE_HEALTH_CHECK_INTERVAL, JOB_CHECK_NODE_LIMITS_INTERVAL


node_operator = NodeOperation(operator_type=OperatorType.SYSTEM)
logger = get_logger("node-checker")


async def verify_node_backend_health(node: PasarGuardNode, node_name: str) -> tuple[Health, int | None, str | None]:
    """
    Verify node health by checking backend stats.
    Returns (health, error_code, error_message) - error_code and error_message are None if no error occurred.
    """
    current_health = await asyncio.wait_for(node.get_health(), timeout=10)

    # Skip nodes that are not connected or invalid
    if current_health in (Health.NOT_CONNECTED, Health.INVALID):
        return current_health, None, None

    try:
        await node.get_backend_stats()
        if current_health != Health.HEALTHY:
            await node.set_health(Health.HEALTHY)
            logger.debug(f"[{node_name}] Node health is HEALTHY")
        return Health.HEALTHY, None, None
    except NodeAPIError as e:
        logger.error(
            f"[{node_name}] Health check failed, setting health to BROKEN | Error: NodeAPIError(code={e.code}) - {e.detail}"
        )
        try:
            await node.set_health(Health.BROKEN)
            return Health.BROKEN, e.code, e.detail
        except Exception as e_set_health:
            error_type_set = type(e_set_health).__name__
            logger.error(
                f"[{node_name}] Failed to set health to BROKEN | Error: {error_type_set} - {str(e_set_health)}"
            )
            return current_health, e.code, e.detail
    except Exception as e:
        error_type = type(e).__name__
        error_message = f"{error_type}: {str(e)}"
        logger.error(f"[{node_name}] Health check failed, setting health to BROKEN | Error: {error_message}")
        try:
            await node.set_health(Health.BROKEN)
            return Health.BROKEN, None, error_message
        except Exception as e_set_health:
            error_type_set = type(e_set_health).__name__
            logger.error(
                f"[{node_name}] Failed to set health to BROKEN | Error: {error_type_set} - {str(e_set_health)}"
            )
            return current_health, None, error_message


async def process_node_health_check(db_node: Node, node: PasarGuardNode):
    """
    Process health check for a single node:
    1. Check if node requires hard reset
    2. Verify backend health
    3. Compare with database status
    4. Update status if needed

    Timeout handling:
    - For timeout errors (code=-1): Don't reconnect, just wait for recovery
    - For other errors (code > -1): Reconnect (connection works but has another issue)
    - For NOT_CONNECTED/INVALID: Reconnect immediately
    """
    if node is None:
        return

    try:
        health, error_code, error_message = await verify_node_backend_health(node, db_node.name)
    except asyncio.TimeoutError:
        # Record timeout error in database but don't reconnect
        logger.warning(f"[{db_node.name}] Health check timed out")
        async with GetDB() as db:
            await NodeOperation._update_single_node_status(
                db, db_node.id, NodeStatus.error, message="Health check timeout"
            )
        return
    except NodeAPIError as e:
        # Record error in database
        async with GetDB() as db:
            await NodeOperation._update_single_node_status(db, db_node.id, NodeStatus.error, message=e.detail)
        # For timeout errors (code=-1), don't reconnect - just wait for recovery
        if e.code == -1:
            logger.warning(f"[{db_node.name}] Health check timed out (NodeAPIError), waiting for recovery")
            return
        # For other errors, reconnect
        async with GetDB() as db:
            await node_operator.connect_single_node(db, db_node.id)
        return

    # Skip nodes that are already healthy and connected
    if health == Health.HEALTHY and db_node.status == NodeStatus.connected:
        return

    # Handle hard reset requirement
    if node.requires_hard_reset():
        async with GetDB() as db:
            await node_operator.connect_single_node(db, db_node.id)
        return

    if health is Health.INVALID:
        logger.warning(f"[{db_node.name}] Node health is INVALID, ignoring...")
        return

    # Handle NOT_CONNECTED - reconnect immediately
    if health is Health.NOT_CONNECTED:
        async with GetDB() as db:
            await node_operator.connect_single_node(db, db_node.id)
        return

    # Handle BROKEN health
    if health == Health.BROKEN:
        # Record actual error in database
        async with GetDB() as db:
            await NodeOperation._update_single_node_status(db, db_node.id, NodeStatus.error, message=error_message)
        # Only reconnect for non-timeout errors (code > -1)
        if error_code is not None and error_code > -1:
            async with GetDB() as db:
                await node_operator.connect_single_node(db, db_node.id)
        # For timeout (code=-1 or None), just wait - don't reconnect
        return

    # Update status for recovering nodes
    if db_node.status in (NodeStatus.connecting, NodeStatus.error) and health == Health.HEALTHY:
        async with GetDB() as db:
            node_version, core_version = await node.get_versions()
            await NodeOperation._update_single_node_status(
                db,
                db_node.id,
                NodeStatus.connected,
                xray_version=core_version,
                node_version=node_version,
            )
        return


async def check_node_limits():
    """
    Check nodes that have exceeded their data limit and update status to limited.
    """

    async with GetDB() as db:
        limited_nodes = await get_limited_nodes(db)

        for db_node in limited_nodes:
            # Disconnect the node first (stop it from running)
            await node_operator.disconnect_single_node(db_node.id)

            # Update status to limited
            await NodeOperation._update_single_node_status(
                db, db_node.id, NodeStatus.limited, message="Data limit exceeded", send_notification=False
            )

            # Send notification
            node_notif = NodeNotification(
                id=db_node.id, name=db_node.name, xray_version=db_node.xray_version, node_version=db_node.node_version
            )
            await notification.limited_node(node_notif, db_node.data_limit, db_node.used_traffic)

            logger.info(f'Node "{db_node.name}" (ID: {db_node.id}) marked as limited due to data limit')


async def node_health_check():
    """
    Cron job that checks health of all enabled nodes.
    """
    async with GetDB() as db:
        db_nodes, _ = await get_nodes(db=db, enabled=True)
        dict_nodes = await node_manager.get_nodes()

        check_tasks = [process_node_health_check(db_node, dict_nodes.get(db_node.id)) for db_node in db_nodes]
        await asyncio.gather(*check_tasks, return_exceptions=True)


@on_startup
async def initialize_nodes():
    logger.info("Starting nodes' cores...")

    async with GetDB() as db:
        db_nodes, _ = await get_nodes(db=db, enabled=True)

        if not db_nodes:
            logger.warning("Attention: You have no node, you need to have at least one node")
        else:
            await node_operator.connect_nodes_bulk(db, db_nodes)
            logger.info("All nodes' cores have been started.")

    # Schedule node health check job (runs frequently)
    scheduler.add_job(
        node_health_check, "interval", seconds=JOB_CORE_HEALTH_CHECK_INTERVAL, coalesce=True, max_instances=1
    )

    # Schedule node limits check job (runs less frequently)
    scheduler.add_job(
        check_node_limits, "interval", seconds=JOB_CHECK_NODE_LIMITS_INTERVAL, coalesce=True, max_instances=1
    )


@on_shutdown
async def shutdown_nodes():
    logger.info("Stopping nodes' cores...")

    nodes: dict[int, PasarGuardNode] = await node_manager.get_nodes()

    stop_tasks = [node.stop() for node in nodes.values()]

    # Run all tasks concurrently and wait for them to complete
    await asyncio.gather(*stop_tasks, return_exceptions=True)

    logger.info("All nodes' cores have been stopped.")
