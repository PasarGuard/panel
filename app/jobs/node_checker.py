import asyncio

from PasarGuardNodeBridge import Health, NodeAPIError, PasarGuardNode
from PasarGuardNodeBridge.storage import LifecycleStatus

from app import notification, on_shutdown, on_startup, scheduler
from app.db import GetDB
from app.db.crud.node import get_limited_nodes, get_node_by_id, get_nodes
from app.db.models import Node, NodeStatus
from app.models.node import NodeListQuery, NodeNotification
from app.nats import is_multi_worker
from app.node import node_manager
from app.node.nats_memory import ensure_bridge_memory, get_bridge_memory, shutdown_bridge_memory
from app.operation import OperatorType
from app.operation.node import NodeOperation
from app.utils.logger import get_logger
from config import feature_settings, job_settings, runtime_settings, server_settings

node_operator = NodeOperation(operator_type=OperatorType.SYSTEM)
logger = get_logger("node-checker")

# Hard-limit concurrency: Prevent DB/API overload during health checks
# Limits concurrent node health check operations
NODE_CHECK_SEM = asyncio.Semaphore(5)  # Max 5 concurrent node health checks
ACTIVE_NODE_STATUSES = [NodeStatus.connected, NodeStatus.connecting, NodeStatus.error]


def should_reconnect_after_health_error(error_code: int | None, error_message: str | None) -> bool:
    if error_code is None:
        return False

    detail = (error_message or "").lower()
    if error_code in {500, 502, 503, 504} and (
        "failed to get sys stats" in detail or "core is not started yet" in detail
    ):
        return False

    return error_code > -1


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
            logger.error(f"[{node_name}] Failed to set health to BROKEN | Error: {error_type_set} - {e_set_health!s}")
            return current_health, e.code, e.detail
    except Exception as e:
        error_type = type(e).__name__
        error_message = f"{error_type}: {e!s}"
        logger.error(f"[{node_name}] Health check failed, setting health to BROKEN | Error: {error_message}")
        try:
            await node.set_health(Health.BROKEN)
            return Health.BROKEN, None, error_message
        except Exception as e_set_health:
            error_type_set = type(e_set_health).__name__
            logger.error(f"[{node_name}] Failed to set health to BROKEN | Error: {error_type_set} - {e_set_health!s}")
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
    _, coordinator, _ = get_bridge_memory()
    bridge_namespace = str(getattr(db_node, "bridge_id", None) or db_node.id)
    if coordinator is not None and await coordinator.is_deleted(bridge_namespace):
        if node is not None:
            await node_manager.remove_node(
                db_node.id,
                remote_stop=False,
                expected_bridge_namespace=bridge_namespace,
            )
        return

    if node is None:
        async with GetDB() as db:
            await node_operator.connect_single_node(db, db_node.id)
        return

    # Broadcast delivery is best-effort. A worker that missed an upsert heals
    # from the authoritative DB row during its ordinary health pass.
    if getattr(node, "_extra", {}).get("config_signature") is not None and not node_manager.runtime_config_matches(
        node, db_node
    ):
        await node_manager.update_node(db_node)
        return

    # Limit concurrent health checks to prevent DB/API overload
    async with NODE_CHECK_SEM:
        # Handle hard reset requirement
        if node.requires_hard_reset():
            async with GetDB() as db:
                await node_operator.connect_single_node(db, db_node.id)
            return

        try:
            health, error_code, error_message = await verify_node_backend_health(node, db_node.name)
        except TimeoutError:
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

        if health is Health.INVALID:
            logger.warning(f"[{db_node.name}] Node health is INVALID, ignoring...")
            return

        # Prefer shared lifecycle state so multi-worker local NOT_CONNECTED does not thrash Start.
        # Trust observed HEALTHY only if we can attach, or another worker still holds an active lease.
        shared_state = await node.get_lifecycle_state()
        if (
            health is Health.NOT_CONNECTED
            and shared_state is not None
            and shared_state.observed is LifecycleStatus.HEALTHY
        ):
            attached = await NodeOperation._attach_if_running(node, db_node.name)
            if attached is not None:
                return

            _, coordinator, _ = get_bridge_memory()
            if coordinator is not None and await coordinator.has_active_lease(bridge_namespace):
                logger.debug(
                    "[%s] Shared lifecycle HEALTHY with active lease; waiting for owner",
                    db_node.name,
                )
                return

            # Stale HEALTHY (owner gone / core unreachable): fall through to reconnect.
            logger.debug(
                "[%s] Shared lifecycle HEALTHY but attach failed and no active lease; reconnecting",
                db_node.name,
            )

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
            if shared_state is not None:
                await node.update_observed_lifecycle(LifecycleStatus.BROKEN, expected_epoch=shared_state.epoch)
            # Let pg-node recover transient Xray API/core failures internally.
            if should_reconnect_after_health_error(error_code, error_message):
                async with GetDB() as db:
                    await node_operator.connect_single_node(db, db_node.id)
            # For timeout (code=-1 or None), just wait - don't reconnect
            return

        # Update status for recovering nodes
        if db_node.status in (NodeStatus.connecting, NodeStatus.error) and health == Health.HEALTHY:
            async with GetDB() as db:
                logger.info(f"Node '{db_node.name}' have been recovered")
                node_version, core_version = await node.get_versions()
                # Connection restored without a hard reset. Suppress the default
                # connect notification and send a distinct "recovered" one instead,
                # so a self-recovery is visibly different from a full reconnect.
                await NodeOperation._update_single_node_status(
                    db,
                    db_node.id,
                    NodeStatus.connected,
                    xray_version=core_version,
                    node_version=node_version,
                    send_notification=False,
                )
            if shared_state is not None:
                await node.update_observed_lifecycle(LifecycleStatus.HEALTHY, expected_epoch=shared_state.epoch)
            await notification.recovered_node(
                NodeNotification(
                    id=db_node.id,
                    name=db_node.name,
                    xray_version=core_version,
                    node_version=node_version,
                )
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
    if not runtime_settings.role.runs_node:
        return
    async with GetDB() as db:
        db_nodes, _ = await get_nodes(db=db, query=NodeListQuery(status=ACTIVE_NODE_STATUSES), load_usage_logs=False)

    dict_nodes = await node_manager.get_nodes()
    check_tasks = [process_node_health_check(db_node, dict_nodes.get(db_node.id)) for db_node in db_nodes]
    await asyncio.gather(*check_tasks, return_exceptions=True)


async def reconcile_orphaned_user_sync():
    """Periodically resolve durable NATS barriers after worker/process crashes."""
    if not runtime_settings.role.runs_node:
        return
    node_ids = list((await node_manager.get_nodes()).keys())
    for node_id in node_ids:
        async with GetDB() as db:
            db_node = await get_node_by_id(db, node_id, load_usage_logs=False)
            if db_node is None:
                continue
            await node_operator.reconcile_orphaned_user_sync(db, db_node)


_node_loop_tasks: list[asyncio.Task] = []


async def _interval_loop(coro, seconds: float, name: str):
    """Run node maintenance on every worker (APScheduler may be leader-only)."""
    while True:
        try:
            await coro()
        except Exception as exc:
            logger.error("Node loop %s failed: %s", name, exc)
        await asyncio.sleep(seconds)


@on_startup
async def initialize_nodes():
    if not runtime_settings.role.runs_node:
        return

    await ensure_bridge_memory()

    logger.info("Starting nodes' cores...")

    async with GetDB() as db:
        db_nodes, _ = await get_nodes(db=db, query=NodeListQuery(status=ACTIVE_NODE_STATUSES), load_usage_logs=False)

        if not db_nodes:
            logger.warning("Attention: You have no node, you need to have at least one node")
        else:
            await node_operator.connect_nodes_bulk(db, db_nodes)
            logger.info("All nodes' cores have been started.")

    from app.nats.leader import needs_job_leader

    if needs_job_leader():
        # Every uvicorn worker must keep local node attachments healthy.
        _node_loop_tasks.append(
            asyncio.create_task(
                _interval_loop(node_health_check, job_settings.core_health_check_interval, "health"),
                name="node_health_loop",
            )
        )
        _node_loop_tasks.append(
            asyncio.create_task(
                _interval_loop(
                    reconcile_orphaned_user_sync,
                    job_settings.core_health_check_interval,
                    "user-sync-recovery",
                ),
                name="node_user_sync_recovery_loop",
            )
        )
    else:
        scheduler.add_job(
            node_health_check,
            "interval",
            seconds=job_settings.core_health_check_interval,
            coalesce=True,
            max_instances=1,
            id="node_health_check",
            replace_existing=True,
        )
        scheduler.add_job(
            reconcile_orphaned_user_sync,
            "interval",
            seconds=job_settings.core_health_check_interval,
            coalesce=True,
            max_instances=1,
            id="reconcile_orphaned_user_sync",
            replace_existing=True,
        )

    # Limit checks mutate node status / disconnect; run only on the leader scheduler.
    scheduler.add_job(
        check_node_limits,
        "interval",
        seconds=job_settings.check_node_limits_interval,
        coalesce=True,
        max_instances=1,
        id="check_node_limits",
        replace_existing=True,
    )

    # Multi-uvicorn workers must not Stop remote cores / clear shared sync queues on exit.
    if feature_settings.stop_nodes_on_shutdown and server_settings.workers <= 1:
        on_shutdown(shutdown_nodes)

    on_shutdown(_stop_node_loops)
    on_shutdown(shutdown_bridge_memory)


async def _stop_node_loops():
    for task in _node_loop_tasks:
        task.cancel()
    if _node_loop_tasks:
        await asyncio.gather(*_node_loop_tasks, return_exceptions=True)
    _node_loop_tasks.clear()


async def shutdown_nodes():
    if not runtime_settings.role.runs_node:
        return
    if is_multi_worker() and server_settings.workers > 1:
        logger.info("Skipping remote node stop on multi-worker shutdown")
        return

    logger.info("Stopping nodes' cores...")

    nodes: dict[int, PasarGuardNode] = await node_manager.get_nodes()

    stop_tasks = [node.stop() for node in nodes.values()]

    # Run all tasks concurrently and wait for them to complete
    await asyncio.gather(*stop_tasks, return_exceptions=True)

    logger.info("All nodes' cores have been stopped.")
