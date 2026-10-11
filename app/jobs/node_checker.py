import asyncio
import time
from dataclasses import dataclass

from PasarGuardNodeBridge import Health, NodeAPIError, PasarGuardNode
from PasarGuardNodeBridge.storage import LifecycleStatus

from app import notification, on_shutdown, on_startup, scheduler
from app.db import GetDB
from app.db.crud.node import get_limited_nodes, get_nodes
from app.db.models import Node, NodeStatus
from app.models.node import NodeListQuery, NodeNotification
from app.nats import is_multi_worker, needs_shared_bridge_memory
from app.nats.leader import is_job_leader, needs_job_leader, set_on_leadership_lost
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
_SYNC_RECOVERY_INTERVAL = 60.0
_sync_recovery_deadlines: dict[int, float] = {}


@dataclass
class _HealthStreak:
    node: PasarGuardNode
    status: NodeStatus
    leader: bool
    failures: int = 0
    successes: int = 0
    broken: bool = False


_health_streaks: dict[int, _HealthStreak] = {}


def _owns_health_checks() -> bool:
    return not needs_job_leader() or is_job_leader()


def _reset_health_streaks() -> None:
    _health_streaks.clear()


def _accept_health(db_node: Node, node: PasarGuardNode, health: Health) -> bool:
    leader = _owns_health_checks()
    streak = _health_streaks.get(db_node.id)
    if streak is None or streak.node is not node or streak.status != db_node.status or streak.leader != leader:
        streak = _health_streaks[db_node.id] = _HealthStreak(node, db_node.status, leader)
    if health is Health.BROKEN:
        streak.successes = 0
        streak.failures = min(streak.failures + 1, job_settings.node_health_fail_threshold)
        accepted = streak.failures >= job_settings.node_health_fail_threshold
        streak.broken = streak.broken or accepted
        return accepted
    streak.failures = 0
    streak.successes = min(streak.successes + 1, job_settings.node_health_recover_threshold)
    if (streak.broken or db_node.status != NodeStatus.connected) and (
        streak.successes < job_settings.node_health_recover_threshold
    ):
        return False
    streak.broken = False
    return True


async def _set_node_health(node: PasarGuardNode, health: Health, node_name: str) -> None:
    try:
        if await node.get_health() != health:
            await node.set_health(health)
    except Exception:
        # A failed local-state write must never turn a failed probe into success.
        logger.exception("[%s] Failed to set node health to %s", node_name, health.name)


async def _repair_node(node_id: int) -> None:
    if not _owns_health_checks():
        return
    async with GetDB() as db:
        await node_operator.connect_single_node(db, node_id, health_check=True)


# pg-node returns these while the HTTP API is up. They are not interchangeable:
# - backend gone: keep-alive/crash already called Disconnect; panel must Start again
# - core still coming up / Xray API blip: another Start would kill that process
_CORE_DEAD_MARKERS = ("backend not initialized",)
_CORE_STARTING_MARKERS = ("core is not started yet", "failed to get sys stats")


def _health_error_matches(error_code: int | None, error_message: str | None, markers: tuple[str, ...]) -> bool:
    if error_code not in {500, 502, 503, 504}:
        return False
    detail = (error_message or "").lower()
    return any(marker in detail for marker in markers)


def is_core_dead_error(error_code: int | None, error_message: str | None) -> bool:
    return _health_error_matches(error_code, error_message, _CORE_DEAD_MARKERS)


def is_core_starting_error(error_code: int | None, error_message: str | None) -> bool:
    return _health_error_matches(error_code, error_message, _CORE_STARTING_MARKERS)


def is_core_not_started_error(error_code: int | None, error_message: str | None) -> bool:
    return is_core_dead_error(error_code, error_message) or is_core_starting_error(error_code, error_message)


def should_reconnect_after_health_error(error_code: int | None, error_message: str | None) -> bool:
    if error_code is None:
        return False

    # Dead-core and still-starting 5xxs are not generic reconnects. The BROKEN
    # handler starts only a missing backend, and only when no Start is in flight.
    if is_core_not_started_error(error_code, error_message):
        return False

    return error_code > -1


async def _start_already_in_progress(db_node: Node, shared_state) -> bool:
    if db_node.id in NodeOperation._in_flight_connects:
        return True
    if shared_state is not None and shared_state.observed is LifecycleStatus.STARTING:
        return True
    _, coordinator, _ = get_bridge_memory()
    return coordinator is not None and await coordinator.has_active_lease(str(db_node.id))


async def verify_node_backend_health(node: PasarGuardNode, node_name: str) -> tuple[Health, int | None, str | None]:
    """
    Verify node health by checking backend stats.
    Returns (health, error_code, error_message) - error_code and error_message are None if no error occurred.
    """
    try:
        current_health = await asyncio.wait_for(node.get_health(), timeout=10)
        if current_health in (Health.NOT_CONNECTED, Health.INVALID):
            return current_health, None, None
        await node.get_backend_stats()
        return Health.HEALTHY, None, None
    except TimeoutError:
        return Health.BROKEN, -1, "Health check timeout"
    except NodeAPIError as exc:
        logger.debug("[%s] Backend health probe failed: %s", node_name, exc.detail)
        return Health.BROKEN, exc.code, exc.detail
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc!s}"
        logger.debug("[%s] Backend health probe failed: %s", node_name, error_message)
        return Health.BROKEN, None, error_message


async def process_node_health_check(db_node: Node, node: PasarGuardNode):
    """Probe every worker's attachment; only the job leader changes shared status."""
    if node is None or db_node.status not in ACTIVE_NODE_STATUSES:
        _health_streaks.pop(db_node.id, None)
        return

    async with NODE_CHECK_SEM:
        try:
            health, error_code, error_message = await verify_node_backend_health(node, db_node.name)
        except TimeoutError:
            health, error_code, error_message = Health.BROKEN, -1, "Health check timeout"
        except NodeAPIError as exc:
            health, error_code, error_message = Health.BROKEN, exc.code, exc.detail
        except Exception:
            _health_streaks.pop(db_node.id, None)
            raise

        if health in (Health.HEALTHY, Health.BROKEN):
            if not _accept_health(db_node, node, health):
                # An explicitly absent backend needs repair immediately; only
                # its downtime reporting waits for the configured threshold.
                if health is Health.BROKEN and is_core_dead_error(error_code, error_message):
                    shared_state = await node.get_lifecycle_state()
                    if _owns_health_checks() and not await _start_already_in_progress(db_node, shared_state):
                        await _set_node_health(node, health, db_node.name)
                        await _repair_node(db_node.id)
                return
            await _set_node_health(node, health, db_node.name)
        else:
            _health_streaks.pop(db_node.id, None)

        # Skip nodes that are already healthy and connected
        if health == Health.HEALTHY and db_node.status == NodeStatus.connected:
            requires_recovery = node.requires_hard_reset()
            if requires_recovery or needs_shared_bridge_memory():
                # A slow user-sync RPC does not mean the backend is dead. Repair
                # this worker's attachment without restarting the core, clearing
                # queued work, or broadcasting reconnects to sibling workers.
                now = time.monotonic()
                if now >= _sync_recovery_deadlines.get(db_node.id, 0):
                    _sync_recovery_deadlines[db_node.id] = now + _SYNC_RECOVERY_INTERVAL
                    if requires_recovery:
                        await NodeOperation._attach_if_running(node, db_node.name)
                    else:
                        # An orphaned claim can expire after the first startup
                        # poll. Retry discovery even without a fresh update;
                        # the live KV index makes empty polls request-free.
                        await NodeOperation._resume_shared_sync(node)
            return

        if health is Health.INVALID:
            logger.warning(f"[{db_node.name}] Node health is INVALID, ignoring...")
            return

        # Prefer shared lifecycle state so multi-worker local NOT_CONNECTED does not thrash Start.
        # A BROKEN observation with desired HEALTHY can be an ambiguous client-side Start
        # timeout: the remote core may have completed startup after the panel gave up.
        shared_state = await node.get_lifecycle_state()
        if (
            health is Health.NOT_CONNECTED
            and shared_state is not None
            and (shared_state.observed is LifecycleStatus.HEALTHY or shared_state.desired is LifecycleStatus.HEALTHY)
        ):
            attached = await NodeOperation._attach_if_running(node, db_node.name)
            if attached is not None:
                return

            _, coordinator, _ = get_bridge_memory()
            if coordinator is not None and await coordinator.has_active_lease(str(db_node.id)):
                logger.debug(
                    "[%s] Shared lifecycle HEALTHY with active lease; waiting for owner",
                    db_node.name,
                )
                return

            # Stale/failed desired-healthy state: fall through to reconnect only after
            # the attach probe and active-lease check have both failed.
            logger.debug(
                "[%s] Shared lifecycle desired HEALTHY but attach failed and no active lease; reconnecting",
                db_node.name,
            )

        # Followers repair local attachments but never restart a core or publish
        # status transitions from independent, potentially conflicting samples.
        if not _owns_health_checks():
            return

        if health is Health.NOT_CONNECTED:
            # Initial connection is a lifecycle operation, not a failed probe.
            # An already-errored node still needs confirmed recovery afterwards.
            if db_node.status == NodeStatus.error:
                await _repair_node(db_node.id)
            else:
                async with GetDB() as db:
                    await node_operator.connect_single_node(db, db_node.id)
            return

        if health is Health.BROKEN:
            async with GetDB() as db:
                updated = await NodeOperation._update_single_node_status(
                    db,
                    db_node.id,
                    NodeStatus.error,
                    message=error_message or "Backend health check failed",
                    expected_status=db_node.status,
                )
            if not updated:
                _health_streaks.pop(db_node.id, None)
                return
            # Check before publishing BROKEN: STARTING is evidence of an operation
            # already in progress and must not be overwritten by its health probe.
            starting = await _start_already_in_progress(db_node, shared_state)
            if not _owns_health_checks():
                return
            if shared_state is not None and not starting:
                await node.update_observed_lifecycle(LifecycleStatus.BROKEN, expected_epoch=shared_state.epoch)
            if not starting and (
                should_reconnect_after_health_error(error_code, error_message)
                or is_core_dead_error(error_code, error_message)
            ):
                await _repair_node(db_node.id)
            return

        if db_node.status in (NodeStatus.connecting, NodeStatus.error) and health is Health.HEALTHY:
            node_version, core_version = await node.get_versions()
            if not _owns_health_checks():
                return
            async with GetDB() as db:
                updated = await NodeOperation._update_single_node_status(
                    db,
                    db_node.id,
                    NodeStatus.connected,
                    xray_version=core_version,
                    node_version=node_version,
                    send_notification=False,
                    expected_status=db_node.status,
                )
            if not updated:
                _health_streaks.pop(db_node.id, None)
                return
            if shared_state is not None:
                await node.update_observed_lifecycle(LifecycleStatus.HEALTHY, expected_epoch=shared_state.epoch)
            logger.info("Node '%s' has recovered", db_node.name)
            await notification.recovered_node(
                NodeNotification(id=db_node.id, name=db_node.name, xray_version=core_version, node_version=node_version)
            )


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
    active_ids = {db_node.id for db_node in db_nodes if db_node.id in dict_nodes}
    for cache in (_sync_recovery_deadlines, _health_streaks):
        for node_id in cache.keys() - active_ids:
            cache.pop(node_id, None)
    check_tasks = [process_node_health_check(db_node, dict_nodes.get(db_node.id)) for db_node in db_nodes]
    results = await asyncio.gather(*check_tasks, return_exceptions=True)
    for db_node, result in zip(db_nodes, results):
        if isinstance(result, Exception):
            _health_streaks.pop(db_node.id, None)
            logger.error("[%s] Health check failed: %s", db_node.name, result, exc_info=result)


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

    startup_log = logger.debug if server_settings.workers > 1 else logger.info
    startup_log("Starting nodes' cores...")

    async with GetDB() as db:
        db_nodes, _ = await get_nodes(db=db, query=NodeListQuery(status=ACTIVE_NODE_STATUSES), load_usage_logs=False)

        if not db_nodes:
            logger.warning("Attention: You have no node, you need to have at least one node")
        else:
            await node_operator.connect_nodes_bulk(db, db_nodes)
            startup_log("All nodes' cores have been started.")

    set_on_leadership_lost(_reset_health_streaks)

    if needs_job_leader():
        # Every uvicorn worker must keep local node attachments healthy.
        _node_loop_tasks.append(
            asyncio.create_task(
                _interval_loop(node_health_check, job_settings.core_health_check_interval, "health"),
                name="node_health_loop",
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
    _reset_health_streaks()
    _sync_recovery_deadlines.clear()


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
