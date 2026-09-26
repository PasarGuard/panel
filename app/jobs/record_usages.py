import asyncio
import math
import random
import time
from collections import defaultdict
from datetime import UTC, datetime as dt, timedelta as td
from weakref import WeakKeyDictionary

from PasarGuardNodeBridge import NodeAPIError, PasarGuardNode
from PasarGuardNodeBridge.common.service_pb2 import StatType
from sqlalchemy.exc import DatabaseError, OperationalError

from app import scheduler
from app.db import GetDB
from app.db.base import engine
from app.jobs._usage_queries import build_node_usage_upsert, build_node_user_usage_upsert
from app.jobs._usage_storage import Receipt, UsageStore
from app.node import node_manager
from app.operation.admin_sync import enforce_admin_limits_now
from app.utils.logger import get_logger
from config import job_settings, runtime_settings, usage_settings

logger = get_logger("record-usages")

# SQLite has one writer; server databases allow a small bounded write pool.
_write_gates = WeakKeyDictionary()
API_SEM = asyncio.Semaphore(10)  # Max 10 concurrent node stats RPCs
USAGE_COEFFICIENT_TTL_S = 60.0
NODE_USER_USAGE_BATCH_SIZE_BY_DIALECT = {
    "mysql": 1_000,
    "sqlite": 400,
}
DEADLOCK_MAX_RETRIES = 5

# Prevent overlapping usage jobs from stacking writes (and deadlocks) when
# node stats calls take longer than the scheduler interval.
_user_usage_running = False
_node_usage_running = False
_usage_coefficient_cache: dict[int, tuple[float, float]] = {}


def _chunked(items: list, size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


async def get_dialect() -> str:
    """Get the database dialect name. Cached after first call since the dialect never changes."""
    if _dialect_cache:
        return _dialect_cache[0]
    async with GetDB() as db:
        dialect = db.bind.dialect.name
    _dialect_cache.append(dialect)
    return dialect


# Simple one-element list used as a mutable cache container (set once, read many times)
_dialect_cache: list[str] = []


def _mysql_errno(err) -> int | None:
    orig = getattr(err, "orig", err)
    args = getattr(orig, "args", None)
    if args and isinstance(args[0], int):
        return args[0]
    return None


def _is_retriable_db_error(err) -> bool:
    errno = _mysql_errno(err)
    if errno in (1213, 1205):
        return True
    orig = getattr(err, "orig", err)
    if (getattr(orig, "sqlstate", None) or getattr(orig, "code", None)) in ("40P01", "40001"):
        return True
    message = str(err).lower()
    return "deadlock" in message or "lock wait timeout" in message or "database is locked" in message


async def _transaction(operation, max_retries: int = DEADLOCK_MAX_RETRIES):
    """Retry the entire unit of work, never individual accounting statements."""
    dialect = await get_dialect()
    connectable = engine
    if dialect == "mysql" and hasattr(engine, "execution_options"):
        connectable = engine.execution_options(isolation_level="READ COMMITTED")
    gate = _write_gates.setdefault(engine, asyncio.Semaphore(1 if dialect == "sqlite" else 3))
    for attempt in range(max_retries):
        try:
            async with gate, connectable.begin() as conn:
                return await operation(conn)
        except (OperationalError, DatabaseError) as exc:
            if not _is_retriable_db_error(exc) or attempt == max_retries - 1:
                raise
            delay = min(0.1 * 2**attempt, 2.0)
            logger.warning("Retrying usage transaction (%s/%s)", attempt + 1, max_retries)
            await asyncio.sleep(delay + random.uniform(0, delay / 2))


async def safe_execute(stmt, params=None, max_retries: int = DEADLOCK_MAX_RETRIES):
    async def execute(conn):
        if params is None:
            await conn.execute(stmt)
        else:
            await conn.execute(stmt, params)

    await _transaction(execute, max_retries)


def _get_time_bucket(now: dt | None = None) -> dt:
    """
    Get 10-minute time bucket instead of hourly to reduce hot row contention.
    This reduces lock contention by 6x (60 minutes / 10 minutes = 6).

    Args:
        now: Optional datetime to use (defaults to current time)

    Returns:
        datetime rounded down to 10-minute bucket
    """
    if now is None:
        now = dt.now(UTC)
    # Round down to 10-minute bucket: minute // 10 * 10
    return now.replace(minute=(now.minute // 10) * 10, second=0, microsecond=0)


async def record_user_stats_batched(all_node_params: dict, usage_coefficients: dict):
    """
    Record user statistics for ALL nodes in a single batched UPSERT operation.
    This eliminates per-node write amplification and reduces lock contention.

    Args:
        all_node_params: Dict mapping node_id -> list of user stat params
        usage_coefficients: Dict mapping node_id -> usage coefficient
    """
    if not all_node_params:
        return

    # Aggregate all params across all nodes into single list
    created_at = _get_time_bucket()
    dialect = await get_dialect()

    # Prepare parameters for all nodes in one batch
    upsert_params = []
    for node_id, params in all_node_params.items():
        if not params:
            continue
        coeff = usage_coefficients.get(node_id, 1.0)
        for p in params:
            upsert_params.append(
                {
                    "uid": int(p["uid"]),
                    "value": int(p["value"] * coeff),
                    "node_id": node_id,
                    "created_at": created_at,
                }
            )

    if not upsert_params:
        return

    # Consistent lock order reduces InnoDB deadlocks across overlapping writers
    upsert_params.sort(key=lambda item: (item["uid"], item["node_id"]))

    batch_size = NODE_USER_USAGE_BATCH_SIZE_BY_DIALECT.get(dialect, len(upsert_params))
    batches = list(_chunked(upsert_params, batch_size))
    if len(batches) > 1:
        logger.debug(
            "Splitting %s node user usage rows into %s %s batches",
            len(upsert_params),
            len(batches),
            dialect,
        )

    # Execute batched UPSERTs with concurrency control
    for batch in batches:
        for stmt, stmt_params in build_node_user_usage_upsert(dialect, batch):
            await safe_execute(stmt, stmt_params)


async def record_node_stats_batched(all_node_params: dict):
    """
    Record node-level statistics for ALL nodes in batched operations.
    This reduces write amplification and lock contention.

    Args:
        all_node_params: Dict mapping node_id -> list of node stat params
    """
    if not all_node_params:
        return

    created_at = _get_time_bucket()
    dialect = await get_dialect()

    # Process each node's stats with concurrency control
    async def _record_single_node(node_id: int, params: list[dict]):
        if not params:
            return

        # Aggregate uplink and downlink from params
        total_up = sum(p.get("up", 0) for p in params)
        total_down = sum(p.get("down", 0) for p in params)

        if not (total_up or total_down):
            return

        upsert_param = {
            "node_id": node_id,
            "created_at": created_at,
            "up": total_up,
            "down": total_down,
        }

        # Execute with concurrency control
        queries = build_node_usage_upsert(dialect, upsert_param)

        async def execute(conn):
            for stmt, stmt_params in queries:
                await conn.execute(stmt, stmt_params)

        await _transaction(execute)

    # Execute all node stats with limited concurrency
    tasks = [_record_single_node(node_id, params) for node_id, params in all_node_params.items()]
    if tasks:
        await asyncio.gather(*tasks)


def _process_users_stats_response(stats_response):
    """Fold positive user counters and report invalid IDs without discarding valid rows."""
    params = defaultdict(int)
    for stat in stats_response.stats:
        if stat.value > 0:
            params[stat.name] += stat.value

    validated_params = []
    invalid_uids = []
    for uid, value in params.items():
        try:
            user_id = int(uid)
            if not 0 < user_id <= 2**63 - 1:
                raise ValueError("UID outside database range")
            validated_params.append({"uid": user_id, "value": value})
        except ValueError, TypeError:
            invalid_uids.append(uid)

    return validated_params, invalid_uids


def _usage_job_hint(interval_env: str, interval: int) -> str:
    return (
        f"Lengthen {interval_env} (currently {interval}s) or cut node stats RPC latency. "
        "Raising UVICORN_WORKERS will not help — only one worker records usage."
    )


async def _await_usage_job(job_name: str, impl, interval: int, interval_env: str) -> None:
    # No global wait_for kill: get_stats uses reset=True, so cancelling mid-run drops traffic.
    start = time.monotonic()
    try:
        await impl()
    except asyncio.CancelledError:
        logger.warning("%s was cancelled", job_name)
        raise
    elapsed = time.monotonic() - start
    if interval > 0 and elapsed > interval:
        logger.warning(
            "%s took %.1fs which exceeds the %ss interval; later ticks will be skipped until this run finishes. %s",
            job_name,
            elapsed,
            interval,
            _usage_job_hint(interval_env, interval),
        )


async def _node_usage_coefficient(node: PasarGuardNode, node_id: int) -> float:
    now = time.monotonic()
    cached = _usage_coefficient_cache.get(node_id)
    if cached is not None and cached[1] > now:
        return cached[0]
    try:
        extra = await node.get_extra()
        coeff = float(extra.get("usage_coefficient", 1)) if extra else 1.0
        if not math.isfinite(coeff) or coeff < 0:
            raise ValueError("Invalid usage coefficient")
    except Exception as exc:
        logger.warning("Failed to get extra data for node %s: %s", node_id, exc)
        if cached is None:
            raise
        coeff = cached[0]
    _usage_coefficient_cache[node_id] = (coeff, now + USAGE_COEFFICIENT_TTL_S)
    return coeff


async def _collect_node_user_usage(node: PasarGuardNode, node_id: int) -> tuple[int, float, list]:
    # Resolve all metadata before the destructive stats RPC.
    coeff = await _node_usage_coefficient(node, node_id)
    stats = [] if _stopping else await get_users_stats(node, node_id)
    return node_id, coeff, stats


async def get_users_stats(node: PasarGuardNode, node_id: int | None = None):
    """Fetch and fold user stats from one node. Dict folding stays on the event loop."""
    node_label = node_id if node_id is not None else getattr(node, "node_id", "unknown")
    try:
        # The stream owns its RPC slot until this response is safely staged.
        stats_response = await node.get_stats(stat_type=StatType.UsersStat, reset=True, timeout=30)
        validated_params, invalid_uids = _process_users_stats_response(stats_response)

        if invalid_uids:
            for uid in invalid_uids:
                logger.warning("Skipping invalid UID: %s", uid)

        return validated_params
    except NodeAPIError as e:
        logger.error("Failed to get users stats from node %s, error: %s", node_label, e.detail)
        raise
    except Exception as e:
        logger.error("Failed to get users stats from node %s, unknown error: %s", node_label, e)
        raise


def _process_outbounds_stats_response(stats_response):
    """Ignore malformed directions and negative counters, never subtract traffic."""
    up = down = 0
    for stat in stats_response.stats:
        if stat.value <= 0:
            continue
        if stat.type == "uplink":
            up += stat.value
        elif stat.type == "downlink":
            down += stat.value
    return [{"up": up, "down": down}] if up or down else []


async def get_outbounds_stats(node: PasarGuardNode, node_id: int | None = None):
    """Fetch and fold outbound stats from one node. Dict folding stays on the event loop."""
    node_label = node_id if node_id is not None else getattr(node, "node_id", "unknown")
    try:
        # Caller holds API_SEM so node RPCs stay bounded.
        stats_response = await node.get_stats(stat_type=StatType.Outbounds, reset=True, timeout=10)
        return _process_outbounds_stats_response(stats_response)
    except NodeAPIError as e:
        logger.error("Failed to get outbounds stats from node %s, error: %s", node_label, e.detail)
        raise
    except Exception as e:
        logger.error("Failed to get outbounds stats from node %s, unknown error: %s", node_label, e)
        raise


# One in-flight sample per node/stream. Failed staging stops further destructive
# reads for that stream; durable receipts are replayed before new samples.
_tasks: dict[tuple[str, int], asyncio.Task] = {}
_unstaged: dict[tuple[str, int], Receipt] = {}
_stopping = False
_enforcement_task: asyncio.Task | None = None
_enforcement_dirty = False


def _request_enforcement():
    global _enforcement_task, _enforcement_dirty
    _enforcement_dirty = True
    if _enforcement_task is None or _enforcement_task.done():
        _enforcement_task = asyncio.create_task(_enforce_limits(), name="usage-admin-limits")
    return _enforcement_task


async def _enforce_limits():
    global _enforcement_dirty
    while _enforcement_dirty:
        _enforcement_dirty = False
        try:
            await enforce_admin_limits_now(logger=logger)
        except Exception:
            logger.exception("Failed to enforce admin limits; next usage tick will retry")
            return


async def _process_stream(kind: str, node_id: int, node):
    key = (kind, node_id)
    start = time.monotonic()
    accounting_attempted = False
    store = UsageStore(_transaction, await get_dialect())
    try:
        async with API_SEM:
            if key in _unstaged:
                await store.stage(_unstaged[key])
                del _unstaged[key]
            accounting_attempted = await store.apply(kind, node_id)
            if node is None or _stopping:
                return
            previous = await store.prepare(kind, node_id)
            if _stopping:
                return
            coefficient = 1.0
            if kind == "users":
                _, coefficient, stats = await _collect_node_user_usage(node, node_id)
            else:
                stats = await get_outbounds_stats(node, node_id)
            if not stats:
                return
            receipt = Receipt.create(
                kind, node_id, previous, stats, not usage_settings.disable_recording_node_usage, coefficient
            )
            _unstaged[key] = receipt
            await store.stage(receipt)
            del _unstaged[key]
            accounting_attempted = True
            await store.apply(kind, node_id)
    except Exception:
        logger.exception("Usage stream %s/%s failed; pending samples will be retried before new reads", kind, node_id)
    finally:
        if kind == "users" and accounting_attempted:
            _request_enforcement()
        elapsed = time.monotonic() - start
        interval = (
            job_settings.record_user_usages_interval if kind == "users" else job_settings.record_node_usages_interval
        )
        if interval > 0 and elapsed > interval:
            logger.warning("Usage stream %s/%s took %.1fs (interval %ss)", kind, node_id, elapsed, interval)


async def _dispatch(kind: str, *, wait: bool):
    if _stopping:
        return
    try:
        nodes = dict(await node_manager.get_healthy_nodes())
    except Exception:
        logger.exception("Node discovery failed; recovering persisted usage without polling nodes")
        nodes = {}
    store = UsageStore(_transaction, await get_dialect())
    pending = await store.pending_nodes(kind)
    if _stopping:
        return
    node_ids = set(nodes) | set(pending) | {nid for stream, nid in _unstaged if stream == kind}
    active = []
    for node_id in sorted(node_ids):
        key = (kind, node_id)
        task = _tasks.get(key)
        if task is None or task.done():
            task = asyncio.create_task(
                _process_stream(kind, node_id, nodes.get(node_id)), name=f"usage-{kind}-{node_id}"
            )
            _tasks[key] = task
            task.add_done_callback(lambda completed, key=key: _stream_done(key, completed))
        active.append(task)
    if wait and active:
        # A cancelled scheduler caller must not cancel a destructive read.
        await asyncio.shield(asyncio.gather(*active))
    if kind == "users":
        enforcement = _request_enforcement()
        if wait:
            await asyncio.shield(enforcement)


def _stream_done(key, task):
    if _tasks.get(key) is task:
        del _tasks[key]
    if not task.cancelled() and task.exception() is not None:
        logger.error("Usage task %s failed: %s", key, task.exception())


async def _record_user_usages_impl():
    await _dispatch("users", wait=True)


async def _record_node_usages_impl():
    await _dispatch("outbounds", wait=True)


async def record_user_usages():
    global _user_usage_running
    if _user_usage_running:
        logger.warning(
            "record_user_usages skipped. %s",
            _usage_job_hint("JOB_RECORD_USER_USAGES_INTERVAL", job_settings.record_user_usages_interval),
        )
        return
    _user_usage_running = True
    try:
        await _await_usage_job(
            "record_user_usages",
            _record_user_usages_impl,
            job_settings.record_user_usages_interval,
            "JOB_RECORD_USER_USAGES_INTERVAL",
        )
    finally:
        _user_usage_running = False


async def record_node_usages():
    global _node_usage_running
    if _node_usage_running:
        logger.warning(
            "record_node_usages skipped. %s",
            _usage_job_hint("JOB_RECORD_NODE_USAGES_INTERVAL", job_settings.record_node_usages_interval),
        )
        return
    _node_usage_running = True
    try:
        await _await_usage_job(
            "record_node_usages",
            _record_node_usages_impl,
            job_settings.record_node_usages_interval,
            "JOB_RECORD_NODE_USAGES_INTERVAL",
        )
    finally:
        _node_usage_running = False


async def _schedule_users():
    await _dispatch("users", wait=False)


async def _schedule_outbounds():
    await _dispatch("outbounds", wait=False)


def resume_usage_recording():
    global _stopping
    _stopping = False


async def drain_usage_recording():
    global _stopping
    _stopping = True
    if _tasks:
        await asyncio.shield(asyncio.gather(*list(_tasks.values()), return_exceptions=True))
    if _enforcement_task is not None:
        await asyncio.shield(_enforcement_task)
    store = UsageStore(_transaction, await get_dialect())
    for key, receipt in list(_unstaged.items()):
        try:
            await store.stage(receipt)
            del _unstaged[key]
        except Exception:
            logger.exception("Unable to persist usage receipt %s during shutdown", receipt.receipt_id)


if runtime_settings.role.runs_node:
    for kind, job, interval, delay in (
        ("user", _schedule_users, job_settings.record_user_usages_interval, 30),
        ("node", _schedule_outbounds, job_settings.record_node_usages_interval, 15),
    ):
        scheduler.add_job(
            job,
            "interval",
            seconds=interval,
            start_date=dt.now(UTC) + td(seconds=delay),
            coalesce=True,
            max_instances=1,
            id=f"record_{kind}_usages",
            replace_existing=True,
        )
