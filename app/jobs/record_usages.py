import asyncio
import random
import time
from collections import defaultdict
from datetime import UTC, datetime as dt, timedelta as td
from operator import attrgetter

from PasarGuardNodeBridge import NodeAPIError, PasarGuardNode
from PasarGuardNodeBridge.common.service_pb2 import StatType
from sqlalchemy import BigInteger, DateTime, and_, bindparam, func, insert, select, union_all, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import ARRAY, insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DatabaseError, OperationalError
from sqlalchemy.sql.expression import Insert

from app import scheduler
from app.db import GetDB
from app.db.base import engine
from app.db.models import Admin, Node, NodeUsage, NodeUserUsage, System, User
from app.node import node_manager
from app.operation.admin_sync import enforce_admin_limits_now
from app.utils.logger import get_logger
from config import job_settings, runtime_settings, usage_settings

logger = get_logger("record-usages")

# Hard-limit concurrency: Prevent DB lock storms
# Start with 2-4, adjust based on DB performance
JOB_SEM = asyncio.Semaphore(3)  # Max 3 concurrent DB write operations
API_SEM = asyncio.Semaphore(10)  # Max 10 concurrent node stats RPCs
USAGE_COEFFICIENT_TTL_S = 60.0
NODE_USER_USAGE_BATCH_SIZE_BY_DIALECT = {
    "mysql": 1_000,
    "sqlite": 400,
}
USER_TRAFFIC_UPDATE_BATCH_SIZE_BY_DIALECT = {
    "mysql": 500,
    "sqlite": 400,
}
USER_ADMIN_LOOKUP_BATCH_SIZE = 1_000
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


def build_node_user_usage_upsert(dialect: str, upsert_params: list[dict]):
    """
    Build UPSERT statement for NodeUserUsage based on database dialect.

    Args:
        dialect: Database dialect name ('postgresql', 'mysql', or 'sqlite')
        upsert_params: List of parameter dicts with keys: uid, node_id, created_at, value

    Returns:
        list: One SQL statement and its bound parameters.
    """
    if dialect == "postgresql":
        source = (
            func.unnest(
                bindparam("uids", type_=ARRAY(BigInteger())),
                bindparam("node_ids", type_=ARRAY(BigInteger())),
                bindparam("created_ats", type_=ARRAY(DateTime(timezone=True))),
                bindparam("traffic_values", type_=ARRAY(BigInteger())),
            )
            .table_valued("uid", "node_id", "created_at", "value")
            .render_derived(name="source")
        )

        select_stmt = (
            select(
                source.c.created_at,
                source.c.uid,
                source.c.node_id,
                func.sum(source.c.value).label("used_traffic"),
            )
            .select_from(source.join(User, User.id == source.c.uid))
            .group_by(source.c.created_at, source.c.uid, source.c.node_id)
        )

        stmt = pg_insert(NodeUserUsage).from_select(
            ["created_at", "user_id", "node_id", "used_traffic"],
            select_stmt,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["created_at", "user_id", "node_id"],
            set_={"used_traffic": NodeUserUsage.used_traffic + stmt.excluded.used_traffic},
        )
        return [
            (
                stmt,
                {
                    "uids": [param["uid"] for param in upsert_params],
                    "node_ids": [param["node_id"] for param in upsert_params],
                    "created_ats": [param["created_at"] for param in upsert_params],
                    "traffic_values": [param["value"] for param in upsert_params],
                },
            )
        ]

    select_parts = []
    stmt_params = {}
    for index, param in enumerate(upsert_params):
        uid_key = f"uid_{index}"
        node_id_key = f"node_id_{index}"
        created_at_key = f"created_at_{index}"
        value_key = f"value_{index}"
        select_parts.append(
            select(
                bindparam(uid_key).label("uid"),
                bindparam(node_id_key).label("node_id"),
                bindparam(created_at_key).label("created_at"),
                bindparam(value_key).label("value"),
            )
        )
        stmt_params[uid_key] = param["uid"]
        stmt_params[node_id_key] = param["node_id"]
        stmt_params[created_at_key] = param["created_at"]
        stmt_params[value_key] = param["value"]

    source = union_all(*select_parts).subquery("source")
    select_stmt = (
        select(
            source.c.created_at,
            source.c.uid,
            source.c.node_id,
            func.sum(source.c.value).label("used_traffic"),
        )
        .select_from(source.join(User, User.id == source.c.uid))
        .group_by(source.c.created_at, source.c.uid, source.c.node_id)
    )

    if dialect == "mysql":
        insert_source = select_stmt.subquery("insert_source")
        insert_select_stmt = select(
            insert_source.c.created_at,
            insert_source.c.uid,
            insert_source.c.node_id,
            insert_source.c.used_traffic,
        )
        stmt = mysql_insert(NodeUserUsage).from_select(
            ["created_at", "user_id", "node_id", "used_traffic"],
            insert_select_stmt,
        )
        stmt = stmt.on_duplicate_key_update(used_traffic=NodeUserUsage.used_traffic + insert_source.c.used_traffic)
        return [(stmt, stmt_params)]

    stmt = sqlite_insert(NodeUserUsage).from_select(
        ["created_at", "user_id", "node_id", "used_traffic"],
        select_stmt,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["created_at", "user_id", "node_id"],
        set_={"used_traffic": NodeUserUsage.used_traffic + stmt.excluded.used_traffic},
    )
    return [(stmt, stmt_params)]


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
    if getattr(orig, "code", None) == "40P01":
        return True
    message = str(err).lower()
    return "deadlock" in message or "lock wait timeout" in message or "database is locked" in message


async def safe_execute(stmt, params=None, max_retries: int = DEADLOCK_MAX_RETRIES):
    """
    Safely execute database operations with deadlock and connection handling.
    Creates a fresh DB session for each retry attempt to release locks.

    Args:
        stmt: SQLAlchemy statement to execute
        params (list[dict], optional): Parameters for the statement
        max_retries (int, optional): Maximum number of attempts including the first
    """
    statement = stmt

    # Get dialect once before retry loop to avoid repeated DB calls
    dialect = await get_dialect()
    if (
        dialect == "mysql"
        and isinstance(stmt, Insert)
        and (not hasattr(stmt, "_post_values_clause") or stmt._post_values_clause is None)
    ):
        # MySQL-specific IGNORE prefix - but skip if using ON DUPLICATE KEY UPDATE
        statement = stmt.prefix_with("IGNORE")

    connectable = engine
    if dialect == "mysql" and hasattr(engine, "execution_options"):
        # READ COMMITTED avoids gap/next-key locks that amplify MySQL deadlocks
        # during concurrent usage updates and upserts.
        connectable = engine.execution_options(isolation_level="READ COMMITTED")

    for attempt in range(max_retries):
        try:
            # engine.begin() ensures commit/rollback + connection return on exit
            async with connectable.begin() as conn:
                if params is None:
                    await conn.execute(statement)
                else:
                    await conn.execute(statement, params)
                return

        except (OperationalError, DatabaseError) as err:
            # Session auto-closed by context manager, locks released
            mysql_errno = _mysql_errno(err)
            is_sqlite_locked = "database is locked" in str(err).lower()

            if attempt < max_retries - 1 and _is_retriable_db_error(err):
                if is_sqlite_locked and attempt > 0:
                    # When SQLite is overloaded, extra retries become a self-DDOS
                    logger.warning("SQLite lock persisted after retry; dropping operation to prevent retry storm")
                    raise

                # Exponential backoff with jitter. Lock-wait timeouts get a longer base delay.
                base_delay = 0.2 * (2**attempt) if mysql_errno == 1205 else 0.1 * (2**attempt)
                jitter = random.uniform(0, base_delay * 0.5)
                logger.warning(
                    "Retrying usage write after %s (attempt %s/%s)",
                    f"MySQL {mysql_errno}" if mysql_errno else err.__class__.__name__,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(base_delay + jitter)
                continue

            if attempt >= max_retries - 1 and _is_retriable_db_error(err):
                logger.error("Usage write failed after %s attempts: %s", max_retries, err)
            raise


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
    async with JOB_SEM:
        for batch in batches:
            queries = build_node_user_usage_upsert(dialect, batch)
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
        params[stat.name] += stat.value

    validated_params = []
    invalid_uids = []
    for uid, value in params.items():
        try:
            validated_params.append({"uid": int(uid), "value": value})
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
        coeff = float(extra.get("usage_coefficient", 1) or 1) if extra else 1.0
    except Exception as exc:
        logger.warning("Failed to get extra data for node %s: %s", node_id, exc)
        coeff = cached[0] if cached is not None else 1.0
    _usage_coefficient_cache[node_id] = (coeff, now + USAGE_COEFFICIENT_TTL_S)
    return coeff


async def _collect_node_user_usage(node: PasarGuardNode, node_id: int) -> tuple[int, float, list]:
    """Fetch coefficient and user stats under one RPC slot so extra+stats overlap."""
    async with API_SEM:
        coeff_result, stats_result = await asyncio.gather(
            _node_usage_coefficient(node, node_id),
            get_users_stats(node, node_id),
            return_exceptions=True,
        )
    if isinstance(coeff_result, Exception):
        logger.warning("Failed to get extra data for node %s: %s", node_id, coeff_result)
        coeff = 1.0
    else:
        coeff = coeff_result
    if isinstance(stats_result, Exception):
        logger.warning("Failed to get stats for node %s: %s", node_id, stats_result)
        stats: list = []
    else:
        stats = stats_result
    return node_id, coeff, stats


async def _bounded_node_rpc(coro):
    async with API_SEM:
        return await coro


async def get_users_stats(node: PasarGuardNode, node_id: int | None = None):
    """Fetch and fold user stats from one node. Dict folding stays on the event loop."""
    node_label = node_id if node_id is not None else getattr(node, "node_id", "unknown")
    try:
        # Caller holds API_SEM so extra+stats can share one slot without deadlock.
        stats_response = await node.get_stats(stat_type=StatType.UsersStat, reset=True, timeout=30)
        validated_params, invalid_uids = _process_users_stats_response(stats_response)

        if invalid_uids:
            for uid in invalid_uids:
                logger.warning("Skipping invalid UID: %s", uid)

        return validated_params
    except NodeAPIError as e:
        logger.error("Failed to get users stats from node %s, error: %s", node_label, e.detail)
        return []
    except Exception as e:
        logger.error("Failed to get users stats from node %s, unknown error: %s", node_label, e)
        return []


def _process_outbounds_stats_response(stats_response):
    """Fold outbound uplink/downlink stats into per-row params."""
    params = [
        {"up": stat.value, "down": 0} if stat.type == "uplink" else {"up": 0, "down": stat.value}
        for stat in filter(attrgetter("value"), stats_response.stats)
    ]
    return params


async def get_outbounds_stats(node: PasarGuardNode, node_id: int | None = None):
    """Fetch and fold outbound stats from one node. Dict folding stays on the event loop."""
    node_label = node_id if node_id is not None else getattr(node, "node_id", "unknown")
    try:
        # Caller holds API_SEM so node RPCs stay bounded.
        stats_response = await node.get_stats(stat_type=StatType.Outbounds, reset=True, timeout=10)
        return _process_outbounds_stats_response(stats_response)
    except NodeAPIError as e:
        logger.error("Failed to get outbounds stats from node %s, error: %s", node_label, e.detail)
        return []
    except Exception as e:
        logger.error("Failed to get outbounds stats from node %s, unknown error: %s", node_label, e)
        return []


async def calculate_admin_usage(users_usage: list) -> tuple[dict, set[int]]:
    if not users_usage:
        return {}, set()

    # Get unique user IDs from users_usage
    uids = {int(user_usage["uid"]) for user_usage in users_usage}

    async with GetDB() as db:
        # Query only relevant users' admin IDs
        user_admin_pairs = []
        for uid_batch in _chunked(list(uids), USER_ADMIN_LOOKUP_BATCH_SIZE):
            stmt = select(User.id, User.admin_id).where(User.id.in_(uid_batch))
            result = await db.execute(stmt)
            user_admin_pairs.extend(result.fetchall())

    user_admin_map = {uid: admin_id for uid, admin_id in user_admin_pairs}

    admin_usage = defaultdict(int)
    for user_usage in users_usage:
        admin_id = user_admin_map.get(int(user_usage["uid"]))
        if admin_id:
            admin_usage[admin_id] += user_usage["value"]

    return admin_usage, set(user_admin_map.keys())


async def calculate_users_usage(api_params: dict, usage_coefficient: dict) -> list:
    """Aggregate user usage across nodes with coefficients applied."""
    if not api_params:
        return []

    users_usage: dict[int, int] = defaultdict(int)
    for node_id, params in api_params.items():
        if not params:
            continue
        coeff = usage_coefficient.get(node_id, 1)
        for param in params:
            users_usage[int(param["uid"])] += int(param["value"] * coeff)

    return [{"uid": uid, "value": value} for uid, value in users_usage.items()]


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
        collected = await asyncio.gather(
            *[_collect_node_user_usage(node, node_id) for node_id, node in nodes],
            return_exceptions=True,
        )
        usage_coefficient = {}
        api_params = {}
        for i, result in enumerate(collected):
            node_id = nodes[i][0]
            if isinstance(result, Exception):
                logger.warning("Failed to collect usage for node %s: %s", node_id, result)
                usage_coefficient[node_id] = 1.0
                api_params[node_id] = []
                continue
            _, coeff, stats = result
            usage_coefficient[node_id] = coeff
            api_params[node_id] = stats

        users_usage = await calculate_users_usage(api_params, usage_coefficient)
        if not users_usage:
            logger.debug("No user usage to record")
            return

        admin_usage, valid_user_ids = await calculate_admin_usage(users_usage)
        if not valid_user_ids:
            logger.warning("Skipping user usage recording; no matching users found for received stats")
            return

        # Filter valid users - only include users with actual non-zero traffic
        valid_users_usage = [
            usage for usage in users_usage if int(usage["uid"]) in valid_user_ids and usage["value"] > 0
        ]

        # Update User table with concurrency control
        if valid_users_usage:
            valid_users_usage.sort(key=lambda item: int(item["uid"]))
            user_stmt = (
                update(User)
                .where(User.id == bindparam("uid"))
                .values(used_traffic=User.used_traffic + bindparam("value"), online_at=dt.now(UTC))
                .execution_options(synchronize_session=False)
            )
            dialect = await get_dialect()
            batch_size = USER_TRAFFIC_UPDATE_BATCH_SIZE_BY_DIALECT.get(dialect, len(valid_users_usage))
            async with JOB_SEM:
                for batch in _chunked(valid_users_usage, batch_size):
                    await safe_execute(user_stmt, batch)
            logger.debug(f"Updated {len(valid_users_usage)} users")

        # Update Admin table with concurrency control
        if admin_usage:
            admin_data = [{"admin_id": aid, "value": val} for aid, val in sorted(admin_usage.items())]
            admin_stmt = (
                update(Admin)
                .where(Admin.id == bindparam("admin_id"))
                .values(used_traffic=Admin.used_traffic + bindparam("value"))
                .execution_options(synchronize_session=False)
            )
            async with JOB_SEM:
                await safe_execute(admin_stmt, admin_data)
            logger.debug(f"Updated {len(admin_data)} admins")
            try:
                await enforce_admin_limits_now(logger=logger)
            except Exception:
                logger.exception("Failed to enforce admin limits after usage recording")
        if usage_settings.disable_recording_node_usage:
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
        logger.debug(
            f"User usage recording completed in {job_duration:.2f}s: "
            f"{len(valid_users_usage)} users, {len(admin_usage)} admins, "
            f"{len(filtered_node_params)} nodes"
        )

    except Exception:
        job_duration = time.time() - job_start_time
        logger.exception(f"User usage recording failed after {job_duration:.2f}s")
        raise


async def record_user_usages():
    """Record user usages. Overlapping ticks are skipped; there is no global kill.

    ``get_stats(..., reset=True)`` zeros node counters, so a 120s cancel after
    that drop can lose traffic. If this job is skipped, lengthen
    JOB_RECORD_USER_USAGES_INTERVAL or cut node RPC latency — extra Uvicorn
    workers will not help.
    """
    global _user_usage_running
    if _user_usage_running:
        logger.warning(
            "record_user_usages skipped; previous run still in progress. %s",
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
        stats_results = await asyncio.gather(
            *[_bounded_node_rpc(get_outbounds_stats(node, node_id)) for node_id, node in nodes],
            return_exceptions=True,
        )
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
            for node_id, node_data in sorted(node_totals.items())
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
        system_update_stmt = update(System).values(
            uplink=System.uplink + total_up, downlink=System.downlink + total_down
        )
        async with JOB_SEM:
            await safe_execute(system_update_stmt)

        if usage_settings.disable_recording_node_usage:
            return

        # Batch all node usage writes
        await record_node_stats_batched(api_params)

        job_duration = time.time() - job_start_time
        logger.debug(
            f"Node usage recording completed in {job_duration:.2f}s: "
            f"{len(node_update_params)} nodes, total: {total_up + total_down} bytes"
        )

    except Exception:
        job_duration = time.time() - job_start_time
        logger.exception(f"Node usage recording failed after {job_duration:.2f}s")
        raise


async def record_node_usages():
    """Record node usages. Same skip rules as ``record_user_usages``."""
    global _node_usage_running
    if _node_usage_running:
        logger.warning(
            "record_node_usages skipped; previous run still in progress. %s",
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


if runtime_settings.role.runs_node:
    scheduler.add_job(
        record_user_usages,
        "interval",
        seconds=job_settings.record_user_usages_interval,
        start_date=dt.now(UTC) + td(seconds=30),
        coalesce=True,
        max_instances=1,
        id="record_user_usages",
        replace_existing=True,
    )

    scheduler.add_job(
        record_node_usages,
        "interval",
        seconds=job_settings.record_node_usages_interval,
        start_date=dt.now(UTC) + td(seconds=15),
        coalesce=True,
        max_instances=1,
        id="record_node_usages",
        replace_existing=True,
    )
