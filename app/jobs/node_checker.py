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
from app.db.crud.node import get_limited_nodes

from config import JOB_CORE_HEALTH_CHECK_INTERVAL, JOB_CHECK_NODE_LIMITS_INTERVAL


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
            logger.debug(f"[{node_name}] Node health is HEALTHY")
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


async def _fetch_node_versions(node: PasarGuardNode, timeout: int = 10, max_retries: int = 2) -> tuple[str, str] | None:
    """Fetch node versions with timeout and retry logic. Returns (xray_version, node_version) or None on failure.
    
    Uses node.info() to fetch fresh versions from the backend instead of relying on cached in-memory versions.
    """
    for attempt in range(max_retries):
        try:
            info = await asyncio.wait_for(node.info(), timeout=timeout)
            if info and info.core_version and info.node_version:
                # Validate versions are non-empty
                xray_version = info.core_version 
                node_version = info.node_version
                
                # Final validation: both versions must be non-empty
                if xray_version and node_version:
                    return xray_version, node_version
            
            # Versions were empty or missing - log and retry if attempts remain
            logger.debug(f"Version fetch returned empty versions, retry {attempt + 1}/{max_retries}")
            
        except asyncio.TimeoutError:
            # Network timeout - node may be slow or unresponsive
            if attempt < max_retries - 1:
                logger.debug(f"Version fetch timeout, retry {attempt + 1}/{max_retries}")
                await asyncio.sleep(1)  # Brief delay before retry to avoid hammering the node
                continue
            # All retries exhausted
            logger.debug("Version fetch timeout after all retries")
            
        except Exception as e:
            # Other errors (connection errors, API errors, etc.)
            if attempt < max_retries - 1:
                logger.debug(f"Version fetch failed: {type(e).__name__} - {str(e)}, retry {attempt + 1}/{max_retries}")
                await asyncio.sleep(1)  # Brief delay before retry
                continue
            # All retries exhausted
            logger.debug(f"Version fetch failed: {type(e).__name__} - {str(e)}")
    
    # All attempts failed - return None to indicate failure
    return None


async def update_node_connection_status(node_id: int, node: PasarGuardNode):
    """
    Update node connection status by getting backend stats and version info.
    Only marks node as connected if both versions are successfully retrieved and non-empty.
    Automatically retries on timeout.
    """
    async with GetDB() as db:
        try:
            # Add timeout handling for backend stats
            try:
                await asyncio.wait_for(node.get_backend_stats(timeout=8), timeout=10)
            except asyncio.TimeoutError:
                logger.warning(f"Node {node_id} backend stats timeout, attempting restart...")
                await NodeOperation._update_single_node_status(
                    db, node_id, NodeStatus.error, message="Backend stats timeout, restarting..."
                )
                await node_operator.connect_single_node(db, node_id)
                return
            
            # Fetch versions with retry on timeout
            versions = await _fetch_node_versions(node)
            if not versions:
                logger.warning(f"Node {node_id} version fetch failed, attempting restart...")
                await NodeOperation._update_single_node_status(
                    db, node_id, NodeStatus.error, message="Failed to fetch versions, restarting..."
                )
                await node_operator.connect_single_node(db, node_id)
                return

            xray_version, node_version = versions
            
            # Validate versions are non-empty before marking as connected
            if not xray_version or not xray_version.strip() or not node_version or not node_version.strip():
                logger.warning(f"Node {node_id} has invalid versions, attempting restart...")
                await NodeOperation._update_single_node_status(
                    db, node_id, NodeStatus.error, message="Versions are empty or invalid, restarting..."
                )
                await node_operator.connect_single_node(db, node_id)
                return
            
            await NodeOperation._update_single_node_status(
                db, node_id, NodeStatus.connected, xray_version=xray_version, node_version=node_version
            )
        except asyncio.TimeoutError:
            logger.warning(f"Node {node_id} connection status update timeout, attempting restart...")
            await NodeOperation._update_single_node_status(
                db, node_id, NodeStatus.error, message="Connection status update timeout, restarting..."
            )
            await node_operator.connect_single_node(db, node_id)
        except NodeAPIError as e:
            if e.code > -3:
                await NodeOperation._update_single_node_status(db, node_id, NodeStatus.error, message=e.detail)
            if e.code > 0 or e.code == -1 or e.code == -3:
                logger.info(f"Node {node_id} API error (code {e.code}), attempting restart...")
                await node_operator.connect_single_node(db, node_id)
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"Failed to update node {node_id} connection status | Error: {error_type} - {str(e)}")
            await NodeOperation._update_single_node_status(
                db, node_id, NodeStatus.error, message=f"{error_type}: {str(e)}"
            )
            # Automatically restart on any exception
            await node_operator.connect_single_node(db, node_id)


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
        async with GetDB() as db:
            await node_operator.connect_single_node(db, db_node.id)
        return

    try:
        health = await asyncio.wait_for(verify_node_backend_health(node, db_node.name), timeout=15)
    except asyncio.TimeoutError:
        logger.warning(f"[{db_node.name}] Health check timeout, attempting automatic restart...")
        async with GetDB() as db:
            await NodeOperation._update_single_node_status(
                db, db_node.id, NodeStatus.error, message="Health check timeout, restarting..."
            )
            # Automatically restart the node on timeout
            await node_operator.connect_single_node(db, db_node.id)
        return
    except NodeAPIError as e:
        async with GetDB() as db:
            await NodeOperation._update_single_node_status(db, db_node.id, NodeStatus.error, message=e.detail)
            if e.code == -1 or e.code == -3 or e.code > 0:
                logger.info(f"[{db_node.name}] Node API error (code {e.code}), attempting automatic restart...")
                await node_operator.connect_single_node(db, db_node.id)
        return

    # Check if node is marked as connected but has empty versions (invalid state)
    if db_node.status == NodeStatus.connected:
        if not db_node.xray_version or not db_node.node_version:
            logger.warning(f"[{db_node.name}] Node marked as connected but has empty versions, reconnecting...")
            async with GetDB() as db:
                await NodeOperation._update_single_node_status(
                    db, db_node.id, NodeStatus.error, message="Versions missing, reconnecting"
                )
                await node_operator.connect_single_node(db, db_node.id)
            return

        # Skip nodes that are already healthy and connected with valid versions
        if health == Health.HEALTHY:
            return

        # Update status for recovering nodes
        if db_node.status in (NodeStatus.connecting, NodeStatus.error) and health == Health.HEALTHY:
            versions = await _fetch_node_versions(node)
            async with GetDB() as db:
                if versions:
                    xray_version, node_version = versions
                    # Validate versions are non-empty before marking as connected
                    if not xray_version or not xray_version.strip() or not node_version or not node_version.strip():
                        await NodeOperation._update_single_node_status(
                            db, db_node.id, NodeStatus.error, message="Versions are empty or invalid during recovery"
                        )
                        await node_operator.connect_single_node(db, db_node.id)
                    else:
                        await NodeOperation._update_single_node_status(
                            db, db_node.id, NodeStatus.connected, xray_version=xray_version, node_version=node_version
                        )
                else:
                    await NodeOperation._update_single_node_status(
                        db, db_node.id, NodeStatus.error, message="Failed to fetch versions during recovery"
                    )
            return

    # For all other cases, update connection status
    await update_node_connection_status(db_node.id, node)


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
        db_nodes = await node_operator.get_db_nodes(db=db, enabled=True)
        dict_nodes = await node_manager.get_nodes()

        check_tasks = [process_node_health_check(db_node, dict_nodes.get(db_node.id)) for db_node in db_nodes]
        await asyncio.gather(*check_tasks, return_exceptions=True)


@on_startup
async def initialize_nodes():
    logger.info("Starting nodes' cores...")

    async with GetDB() as db:
        db_nodes = await node_operator.get_db_nodes(db=db, enabled=True)

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
