import asyncio
import multiprocessing
import random
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime as dt, timedelta as td, timezone as tz
from operator import attrgetter

from PasarGuardNodeBridge import NodeAPIError, PasarGuardNode
from PasarGuardNodeBridge.common.service_pb2 import StatType
from sqlalchemy import and_, bindparam, insert, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DatabaseError, OperationalError
from sqlalchemy.sql.expression import Insert

from app import on_shutdown, scheduler
from app.db import GetDB
from app.db.base import engine
from app.db.models import Admin, Node, NodeUsage, NodeUserUsage, System, User
from app.node import node_manager
from app.utils.logger import get_logger
from config import (
    DISABLE_RECORDING_NODE_USAGE,
    JOB_RECORD_NODE_USAGES_INTERVAL,
    JOB_RECORD_USER_USAGES_INTERVAL,
)

logger = get_logger("record-usages")

# Hard-limit concurrency: Prevent DB lock storms
# Start with 2-4, adjust based on DB performance
JOB_SEM = asyncio.Semaphore(3)  # Max 3 concurrent DB write operations

# Track running jobs for adaptive scheduling
_running_jobs = {}

# Process pool executor for CPU-bound operations
# Use number of CPU cores, but cap at reasonable limit to avoid overhead
_process_pool = None
_process_pool_lock = asyncio.Lock()

# Thread pool executor for I/O-bound node API calls
# Distributes workload across threads/cores for data collection
_thread_pool = None
_thread_pool_lock = asyncio.Lock()


async def _get_process_pool():
    """Get or create the process pool executor (thread-safe)."""
    global _process_pool
    async with _process_pool_lock:
        if _process_pool is None:
            num_workers = min(multiprocessing.cpu_count(), 8)  # Cap at 8 workers
            _process_pool = ProcessPoolExecutor(max_workers=num_workers)
            logger.info(f"Initialized ProcessPoolExecutor with {num_workers} workers")
        return _process_pool


async def _get_thread_pool():
    """Get or create the thread pool executor (thread-safe)."""
    global _thread_pool
    async with _thread_pool_lock:
        if _thread_pool is None:
            # Use more threads for I/O-bound operations (2x CPU cores, cap at 16)
            num_workers = min(multiprocessing.cpu_count() * 2, 16)
            _thread_pool = ThreadPoolExecutor(max_workers=num_workers)
            logger.info(f"Initialized ThreadPoolExecutor with {num_workers} workers")
        return _thread_pool


@on_shutdown
async def _cleanup_process_pool():
    """Cleanup process pool on shutdown (thread-safe)."""
    global _process_pool
    async with _process_pool_lock:
        if _process_pool is not None:
            logger.info("Shutting down ProcessPoolExecutor...")
            _process_pool.shutdown(wait=True)
            _process_pool = None
            logger.info("ProcessPoolExecutor shut down successfully")


@on_shutdown
async def _cleanup_thread_pool():
    """Cleanup thread pool on shutdown (thread-safe)."""
    global _thread_pool
    async with _thread_pool_lock:
        if _thread_pool is not None:
            logger.info("Shutting down ThreadPoolExecutor...")
            _thread_pool.shutdown(wait=True)
            _thread_pool = None
            logger.info("ThreadPoolExecutor shut down successfully")


# Helper functions for threading (lightweight operations that release GIL)
def _process_node_chunk(chunk_data: tuple) -> dict:
    """
    Process a chunk of node data - lightweight CPU operation.
    Uses simple arithmetic and dict operations that release GIL, perfect for threads.
    """
    node_id, params, coeff = chunk_data
    users_usage = defaultdict(int)
    for param in params:
        uid = int(param["uid"])
        value = int(param["value"] * coeff)
        users_usage[uid] += value
    return dict(users_usage)


def _merge_usage_dicts(dicts: list[dict]) -> dict:
    """
    Merge multiple usage dictionaries.
    Dict operations release GIL, perfect for ThreadPoolExecutor.
    """
    merged = defaultdict(int)
    for d in dicts:
        for uid, value in d.items():
            merged[uid] += value
    return dict(merged)


async def get_dialect() -> str:
    """Get the database dialect name without holding the session open."""
    async with GetDB() as db:
        return db.bind.dialect.name


def build_node_user_usage_upsert(dialect: str, upsert_params: list[dict]):
    """
    Build UPSERT statement for NodeUserUsage based on database dialect.

    Args:
        dialect: Database dialect name ('postgresql', 'mysql', or 'sqlite')
        upsert_params: List of parameter dicts with keys: uid, node_id, created_at, value

    Returns:
        tuple: (statements_list, params_list) - For SQLite returns 2 statements, others return 1
    """
    if dialect == "postgresql":
        stmt = pg_insert(NodeUserUsage).values(
            user_id=bindparam("uid"),
            node_id=bindparam("node_id"),
            created_at=bindparam("created_at"),
            used_traffic=bindparam("value"),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["created_at", "user_id", "node_id"],
            set_={"used_traffic": NodeUserUsage.used_traffic + bindparam("value")},
        )
        return [(stmt, upsert_params)]

    elif dialect == "mysql":
        stmt = mysql_insert(NodeUserUsage).values(
            user_id=bindparam("uid"),
            node_id=bindparam("node_id"),
            created_at=bindparam("created_at"),
            used_traffic=bindparam("value"),
        )
        stmt = stmt.on_duplicate_key_update(used_traffic=NodeUserUsage.used_traffic + stmt.inserted.used_traffic)
        return [(stmt, upsert_params)]

    else:  # SQLite
        # Insert with OR IGNORE
        insert_stmt = (
            insert(NodeUserUsage)
            .values(
                user_id=bindparam("uid"),
                node_id=bindparam("node_id"),
                created_at=bindparam("created_at"),
                used_traffic=0,
            )
            .prefix_with("OR IGNORE")
        )

        # Update with renamed bindparams to avoid conflicts
        update_stmt = (
            update(NodeUserUsage)
            .values(used_traffic=NodeUserUsage.used_traffic + bindparam("value"))
            .where(
                and_(
                    NodeUserUsage.user_id == bindparam("b_uid"),
                    NodeUserUsage.node_id == bindparam("b_node_id"),
                    NodeUserUsage.created_at == bindparam("b_created_at"),
                )
            )
        )

        # Remap params for update statement
        update_params = [
            {
                "value": p["value"],
                "b_uid": p["uid"],
                "b_node_id": p["node_id"],
                "b_created_at": p["created_at"],
            }
            for p in upsert_params
        ]

        return [(insert_stmt, upsert_params), (update_stmt, update_params)]


def build_node_usage_upsert(dialect: str, upsert_param: dict):
    """
    Build UPSERT statement for NodeUsage based on database dialect.

    Args:
        dialect: Database dialect name ('postgresql', 'mysql', or 'sqlite')
        upsert_param: Parameter dict with keys: node_id, created_at, up, down

    Returns:
        tuple: (statements_list, params_list) - For SQLite returns 2 statements, others return 1
    """
    if dialect == "postgresql":
        stmt = pg_insert(NodeUsage).values(
            node_id=bindparam("node_id"),
            created_at=bindparam("created_at"),
            uplink=bindparam("up"),
            downlink=bindparam("down"),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["created_at", "node_id"],
            set_={
                "uplink": NodeUsage.uplink + bindparam("up"),
                "downlink": NodeUsage.downlink + bindparam("down"),
            },
        )
        return [(stmt, [upsert_param])]

    elif dialect == "mysql":
        stmt = mysql_insert(NodeUsage).values(
            node_id=bindparam("node_id"),
            created_at=bindparam("created_at"),
            uplink=bindparam("up"),
            downlink=bindparam("down"),
        )
        stmt = stmt.on_duplicate_key_update(
            uplink=NodeUsage.uplink + stmt.inserted.uplink,
            downlink=NodeUsage.downlink + stmt.inserted.downlink,
        )
        return [(stmt, [upsert_param])]

    else:  # SQLite
        # Insert with OR IGNORE
        insert_stmt = (
            insert(NodeUsage)
            .values(
                node_id=bindparam("node_id"),
                created_at=bindparam("created_at"),
                uplink=0,
                downlink=0,
            )
            .prefix_with("OR IGNORE")
        )

        # Update with renamed bindparams to avoid conflicts
        update_stmt = (
            update(NodeUsage)
            .values(
                uplink=NodeUsage.uplink + bindparam("up"),
                downlink=NodeUsage.downlink + bindparam("down"),
            )
            .where(
                and_(
                    NodeUsage.node_id == bindparam("b_node_id"),
                    NodeUsage.created_at == bindparam("b_created_at"),
                )
            )
        )

        # Remap params for update statement
        update_param = {
            "up": upsert_param["up"],
            "down": upsert_param["down"],
            "b_node_id": upsert_param["node_id"],
            "b_created_at": upsert_param["created_at"],
        }

        return [(insert_stmt, [upsert_param]), (update_stmt, [update_param])]


async def safe_execute(stmt, params=None, max_retries: int = 2):
    """
    Safely execute database operations with deadlock and connection handling.
    Creates a fresh DB session for each retry attempt to release locks.
    
    Reduced retries to prevent retry amplification under load.
    Dropping some stats is better than crashing the system.

    Args:
        stmt: SQLAlchemy statement to execute
        params (list[dict], optional): Parameters for the statement
        max_retries (int, optional): Maximum number of retry attempts (default: 2)
    """
    statement = stmt

    # Get dialect once before retry loop to avoid repeated DB calls
    dialect = await get_dialect()
    if dialect == "mysql" and isinstance(stmt, Insert):
        # MySQL-specific IGNORE prefix - but skip if using ON DUPLICATE KEY UPDATE
        if not hasattr(stmt, "_post_values_clause") or stmt._post_values_clause is None:
            statement = stmt.prefix_with("IGNORE")

    for attempt in range(max_retries):
        try:
            # engine.begin() ensures commit/rollback + connection return on exit
            async with engine.begin() as conn:
                if params is None:
                    await conn.execute(statement)
                else:
                    await conn.execute(statement, params)
                return

        except (OperationalError, DatabaseError) as err:
            # Session auto-closed by context manager, locks released

            # Determine error type for retry logic
            is_mysql_deadlock = (
                hasattr(err, "orig")
                and hasattr(err.orig, "args")
                and len(err.orig.args) > 0
                and err.orig.args[0] == 1213
            )
            is_pg_deadlock = hasattr(err, "orig") and hasattr(err.orig, "code") and err.orig.code == "40P01"
            is_sqlite_locked = "database is locked" in str(err)

            # Retry with exponential backoff if retriable error
            if attempt < max_retries - 1:
                if is_mysql_deadlock or is_pg_deadlock:
                    # Exponential backoff with jitter: 50-75ms, 100-150ms
                    base_delay = 0.05 * (2**attempt)
                    jitter = random.uniform(0, base_delay * 0.5)
                    await asyncio.sleep(base_delay + jitter)
                    continue
                elif is_sqlite_locked:
                    # SQLite locks: only retry once, then fail fast
                    # When DB is overloaded, retries = self-DDOS
                    if attempt == 0:
                        await asyncio.sleep(0.05)
                        continue
                    # After first retry, fail immediately
                    logger.warning("SQLite lock persisted after retry; dropping operation to prevent retry storm")
                    raise

            # If we've exhausted retries or it's not a retriable error, raise
            raise


def _get_time_bucket(now: dt = None) -> dt:
    """
    Get 10-minute time bucket instead of hourly to reduce hot row contention.
    This reduces lock contention by 6x (60 minutes / 10 minutes = 6).
    
    Args:
        now: Optional datetime to use (defaults to current time)
    
    Returns:
        datetime rounded down to 10-minute bucket
    """
    if now is None:
        now = dt.now(tz.utc)
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
            upsert_params.append({
                "uid": int(p["uid"]),
                "value": int(p["value"] * coeff),
                "node_id": node_id,
                "created_at": created_at,
            })
    
    if not upsert_params:
        return
    
    # Execute single batched UPSERT with concurrency control
    async with JOB_SEM:
        queries = build_node_user_usage_upsert(dialect, upsert_params)
        for stmt, stmt_params in queries:
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
        async with JOB_SEM:
            queries = build_node_usage_upsert(dialect, upsert_param)
            for stmt, stmt_params in queries:
                await safe_execute(stmt, stmt_params)
    
    # Execute all node stats with limited concurrency
    tasks = [_record_single_node(node_id, params) for node_id, params in all_node_params.items()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def _process_users_stats_response(stats_response):
    """
    Process stats response (CPU-bound operation) - runs in thread pool.
    Pure function designed for thread-safe execution.
    Returns tuple: (validated_params, invalid_uids) for logging outside thread.
    """
    params = defaultdict(int)
    for stat in filter(attrgetter("value"), stats_response.stats):
        params[stat.name.split(".", 1)[0]] += stat.value

    # Validate UIDs and filter out invalid ones
    validated_params = []
    invalid_uids = []
    for uid, value in params.items():
        try:
            uid_int = int(uid)
            validated_params.append({"uid": uid_int, "value": value})
        except (ValueError, TypeError):
            # Collect invalid UIDs to log outside thread
            invalid_uids.append(uid)
            continue

    return validated_params, invalid_uids


async def get_users_stats(node: PasarGuardNode):
    """
    Get user stats from node using thread pool for CPU-bound processing.
    This distributes the heavy data processing workload across cores.
    """
    async with JOB_SEM:
        try:
            # I/O operation: fetch stats from node (async, non-blocking)
            stats_response = await node.get_stats(stat_type=StatType.UsersStat, reset=True, timeout=30)
            
            # CPU-bound operation: process stats in thread pool to utilize multiple cores
            loop = asyncio.get_running_loop()
            thread_pool = await _get_thread_pool()
            validated_params, invalid_uids = await loop.run_in_executor(
                thread_pool, _process_users_stats_response, stats_response
            )
            
            # Log invalid UIDs outside of thread (thread-safe logging)
            if invalid_uids:
                for uid in invalid_uids:
                    logger.warning("Skipping invalid UID: %s", uid)
            
            return validated_params
        except NodeAPIError as e:
            logger.error("Failed to get users stats, error: %s", e.detail)
            return []
        except Exception as e:
            logger.error("Failed to get users stats, unknown error: %s", e)
            return []


def _process_outbounds_stats_response(stats_response):
    """
    Process outbounds stats response (CPU-bound operation) - can run in thread pool.
    Extracted to separate function for threading.
    """
    params = [
        {"up": stat.value, "down": 0} if stat.type == "uplink" else {"up": 0, "down": stat.value}
        for stat in filter(attrgetter("value"), stats_response.stats)
    ]
    return params


async def get_outbounds_stats(node: PasarGuardNode):
    """
    Get outbounds stats from node using thread pool for CPU-bound processing.
    This distributes the heavy data processing workload across cores.
    """
    async with JOB_SEM:
        try:
            # I/O operation: fetch stats from node (async, non-blocking)
            stats_response = await node.get_stats(stat_type=StatType.Outbounds, reset=True, timeout=10)
            
            # CPU-bound operation: process stats in thread pool to utilize multiple cores
            loop = asyncio.get_running_loop()
            thread_pool = await _get_thread_pool()
            params = await loop.run_in_executor(
                thread_pool, _process_outbounds_stats_response, stats_response
            )
            
            return params
        except NodeAPIError as e:
            logger.error("Failed to get outbounds stats, error: %s", e.detail)
            return []
        except Exception as e:
            logger.error("Failed to get outbounds stats, unknown error: %s", e)
            return []


async def calculate_admin_usage(users_usage: list) -> tuple[dict, set[int]]:
    if not users_usage:
        return {}, set()

    # Get unique user IDs from users_usage
    uids = {int(user_usage["uid"]) for user_usage in users_usage}

    async with GetDB() as db:
        # Query only relevant users' admin IDs
        stmt = select(User.id, User.admin_id).where(User.id.in_(uids))
        result = await db.execute(stmt)
        user_admin_pairs = result.fetchall()

    user_admin_map = {uid: admin_id for uid, admin_id in user_admin_pairs}

    admin_usage = defaultdict(int)
    for user_usage in users_usage:
        admin_id = user_admin_map.get(int(user_usage["uid"]))
        if admin_id:
            admin_usage[admin_id] += user_usage["value"]

    return admin_usage, set(user_admin_map.keys())


async def calculate_users_usage(api_params: dict, usage_coefficient: dict) -> list:
    """Calculate aggregated user usage across all nodes with coefficients applied.
    
    Uses ThreadPoolExecutor for lightweight operations (dict/arithmetic that release GIL).
    ThreadPoolExecutor is faster than ProcessPoolExecutor for these operations due to less overhead.
    """
    if not api_params:
        return []

    def _process_usage_sync(chunks_data: list[tuple[int, list[dict], float]]):
        """Synchronous fallback used for small batches or on executor failures."""
        users_usage = defaultdict(int)
        for _, params, coeff in chunks_data:
            for param in params:
                uid = int(param["uid"])
                value = int(param["value"] * coeff)
                users_usage[uid] += value
        return [{"uid": uid, "value": value} for uid, value in users_usage.items()]

    # Prepare chunks for parallel processing
    chunks = [
        (node_id, params, usage_coefficient.get(node_id, 1))
        for node_id, params in api_params.items()
        if params  # Skip empty params
    ]

    if not chunks:
        return []

    # For small datasets, process synchronously to avoid overhead
    total_params = sum(len(params) for _, params, _ in chunks)
    if total_params < 1000:
        return _process_usage_sync(chunks)

    # Large dataset - use ThreadPoolExecutor (faster for lightweight operations)
    loop = asyncio.get_running_loop()
    try:
        thread_pool = await _get_thread_pool()
    except Exception:
        logger.exception("Falling back to synchronous user usage calculation: failed to init thread pool")
        return _process_usage_sync(chunks)

    try:
        # Process chunks in parallel using threads (less overhead than processes)
        tasks = [loop.run_in_executor(thread_pool, _process_node_chunk, chunk) for chunk in chunks]
        chunk_results = await asyncio.gather(*tasks)

        # Merge results - also lightweight, use threads
        if len(chunk_results) > 4:
            # Split merge operation into smaller chunks
            chunk_size = max(1, len(chunk_results) // 4)
            merge_chunks = [
                chunk_results[i : i + chunk_size]
                for i in range(0, len(chunk_results), chunk_size)
            ]
            merge_tasks = [
                loop.run_in_executor(thread_pool, _merge_usage_dicts, merge_chunk)
                for merge_chunk in merge_chunks
            ]
            partial_results = await asyncio.gather(*merge_tasks)
            final_result = _merge_usage_dicts(partial_results)
        else:
            final_result = _merge_usage_dicts(chunk_results)

        return [{"uid": uid, "value": value} for uid, value in final_result.items()]
    except Exception:
        logger.exception("Falling back to synchronous user usage calculation: executor merge failed")
        return _process_usage_sync(chunks)


async def _record_user_usages_impl():
    """
    Internal implementation of record_user_usages.
    Separated to allow timeout wrapper.
    """
    job_start_time = time.time()
    nodes: tuple[int, PasarGuardNode] = await node_manager.get_healthy_nodes()
    
    if not nodes:
        logger.debug("No healthy nodes found, skipping user usage recording")
        return
    
    logger.debug(f"Starting user usage recording for {len(nodes)} nodes")
    
    try:
        # Gather node extra data directly without unnecessary task creation
        node_data = await asyncio.gather(*[node.get_extra() for _, node in nodes], return_exceptions=True)
        usage_coefficient = {}
        for (node_id, _), data in zip(nodes, node_data):
            if isinstance(data, Exception):
                logger.warning(f"Failed to get extra data for node {node_id}: {data}")
                usage_coefficient[node_id] = 1.0
            else:
                usage_coefficient[node_id] = data.get("usage_coefficient", 1) if data else 1.0

        # Gather stats directly - asyncio.gather accepts coroutines, no need for create_task
        stats_results = await asyncio.gather(*[get_users_stats(node) for _, node in nodes], return_exceptions=True)
        api_params = {}
        for i, result in enumerate(stats_results):
            node_id = nodes[i][0]
            if isinstance(result, Exception):
                logger.warning(f"Failed to get stats for node {node_id}: {result}")
                api_params[node_id] = []
            else:
                api_params[node_id] = result

        users_usage = await calculate_users_usage(api_params, usage_coefficient)
        if not users_usage:
            logger.debug("No user usage to record")
            return

        admin_usage, valid_user_ids = await calculate_admin_usage(users_usage)
        if not valid_user_ids:
            logger.warning("Skipping user usage recording; no matching users found for received stats")
            return

        # Filter valid users - simple operation, no need to parallelize
        valid_users_usage = [usage for usage in users_usage if int(usage["uid"]) in valid_user_ids]
        
        # Update User table with concurrency control
        if valid_users_usage:
            user_stmt = (
                update(User)
                .where(User.id == bindparam("uid"))
                .values(used_traffic=User.used_traffic + bindparam("value"), online_at=dt.now(tz.utc))
                .execution_options(synchronize_session=False)
            )
            async with JOB_SEM:
                await safe_execute(user_stmt, valid_users_usage)
            logger.debug(f"Updated {len(valid_users_usage)} users")

        # Update Admin table with concurrency control
        if admin_usage:
            admin_data = [{"admin_id": aid, "value": val} for aid, val in admin_usage.items()]
            admin_stmt = (
                update(Admin)
                .where(Admin.id == bindparam("admin_id"))
                .values(used_traffic=Admin.used_traffic + bindparam("value"))
                .execution_options(synchronize_session=False)
            )
            async with JOB_SEM:
                await safe_execute(admin_stmt, admin_data)
            logger.debug(f"Updated {len(admin_data)} admins")

        if DISABLE_RECORDING_NODE_USAGE:
            return

        # Batch all node user usage writes into single operation
        # Filter params to only valid users
        filtered_node_params = {}
        for node_id, params in api_params.items():
            filtered_params = [param for param in params if int(param["uid"]) in valid_user_ids]
            if filtered_params:
                filtered_node_params[node_id] = filtered_params
        
        if filtered_node_params:
            await record_user_stats_batched(filtered_node_params, usage_coefficient)
            total_records = sum(len(params) for params in filtered_node_params.values())
            logger.debug(f"Recorded {total_records} node user usage records across {len(filtered_node_params)} nodes")
        
        job_duration = time.time() - job_start_time
        logger.info(
            f"User usage recording completed in {job_duration:.2f}s: "
            f"{len(valid_users_usage)} users, {len(admin_usage)} admins, "
            f"{len(filtered_node_params)} nodes"
        )
        
    except Exception as e:
        job_duration = time.time() - job_start_time
        logger.error(f"User usage recording failed after {job_duration:.2f}s: {e}", exc_info=True)
        raise


async def record_user_usages():
    """
    Record user usages with hard timeout to prevent scheduler backlog.
    Wraps the actual implementation with timeout protection.
    """
    # Check if previous run is still active (adaptive scheduling)
    if _running_jobs.get("record_user_usages"):
        logger.warning("Previous record_user_usages run still active; skipping this cycle")
        return
    
    _running_jobs["record_user_usages"] = True
    try:
        # Hard timeout: prevent job from running longer than interval
        # This prevents scheduler backlog → spike → crash
        try:
            await asyncio.wait_for(_record_user_usages_impl(), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("record_user_usages timed out after 30s; skipping cycle to prevent backlog")
    finally:
        _running_jobs["record_user_usages"] = False


async def _record_node_usages_impl():
    """
    Internal implementation of record_node_usages.
    Separated to allow timeout wrapper.
    """
    job_start_time = time.time()
    nodes = await node_manager.get_healthy_nodes()
    
    if not nodes:
        logger.debug("No healthy nodes found, skipping node usage recording")
        return
    
    logger.debug(f"Starting node usage recording for {len(nodes)} nodes")
    
    try:
        # Get healthy nodes and gather stats directly
        stats_results = await asyncio.gather(*[get_outbounds_stats(node) for _, node in nodes], return_exceptions=True)
        api_params = {}
        for i, result in enumerate(stats_results):
            node_id = nodes[i][0]
            if isinstance(result, Exception):
                logger.warning(f"Failed to get outbounds stats for node {node_id}: {result}")
                api_params[node_id] = []
            else:
                api_params[node_id] = result

        # Calculate per-node totals
        node_totals = {
            node_id: {
                "up": sum(param["up"] for param in params),
                "down": sum(param["down"] for param in params),
            }
            for node_id, params in api_params.items()
        }

        # Calculate system totals from node totals
        total_up = sum(node_data["up"] for node_data in node_totals.values())
        total_down = sum(node_data["down"] for node_data in node_totals.values())

        if not (total_up or total_down):
            logger.debug("No node usage to record")
            return

        # Update each node's uplink/downlink with concurrency control
        node_update_params = [
            {"node_id": node_id, "up": node_data["up"], "down": node_data["down"]}
            for node_id, node_data in node_totals.items()
            if node_data["up"] or node_data["down"]
        ]

        if node_update_params:
            node_update_stmt = (
                update(Node)
                .where(Node.id == bindparam("node_id"))
                .values(uplink=Node.uplink + bindparam("up"), downlink=Node.downlink + bindparam("down"))
                .execution_options(synchronize_session=False)
            )
            async with JOB_SEM:
                await safe_execute(node_update_stmt, node_update_params)
            logger.debug(f"Updated {len(node_update_params)} nodes")

        # Update system totals with concurrency control
        system_update_stmt = update(System).values(uplink=System.uplink + total_up, downlink=System.downlink + total_down)
        async with JOB_SEM:
            await safe_execute(system_update_stmt)

        if DISABLE_RECORDING_NODE_USAGE:
            return

        # Batch all node usage writes
        await record_node_stats_batched(api_params)
        
        job_duration = time.time() - job_start_time
        logger.info(
            f"Node usage recording completed in {job_duration:.2f}s: "
            f"{len(node_update_params)} nodes, total: {total_up + total_down} bytes"
        )
        
    except Exception as e:
        job_duration = time.time() - job_start_time
        logger.error(f"Node usage recording failed after {job_duration:.2f}s: {e}", exc_info=True)
        raise


async def record_node_usages():
    """
    Record node usages with hard timeout to prevent scheduler backlog.
    Wraps the actual implementation with timeout protection.
    """
    # Check if previous run is still active (adaptive scheduling)
    if _running_jobs.get("record_node_usages"):
        logger.warning("Previous record_node_usages run still active; skipping this cycle")
        return
    
    _running_jobs["record_node_usages"] = True
    try:
        # Hard timeout: prevent job from running longer than interval
        # This prevents scheduler backlog → spike → crash
        try:
            await asyncio.wait_for(_record_node_usages_impl(), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("record_node_usages timed out after 30s; skipping cycle to prevent backlog")
    finally:
        _running_jobs["record_node_usages"] = False


scheduler.add_job(
    record_user_usages,
    "interval",
    seconds=JOB_RECORD_USER_USAGES_INTERVAL,
    coalesce=True,
    start_date=dt.now(tz.utc) + td(seconds=30),
    max_instances=1,
)

scheduler.add_job(
    record_node_usages,
    "interval",
    seconds=JOB_RECORD_NODE_USAGES_INTERVAL,
    coalesce=True,
    start_date=dt.now(tz.utc) + td(seconds=15),
    max_instances=1,
)
