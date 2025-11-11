import asyncio
import random
from collections import defaultdict
from datetime import datetime as dt, timezone as tz, timedelta as td
from operator import attrgetter

from PasarGuardNodeBridge import PasarGuardNode, NodeAPIError
from PasarGuardNodeBridge.common.service_pb2 import StatType
from sqlalchemy import and_, bindparam, insert, select, update
from sqlalchemy.exc import DatabaseError, OperationalError
from sqlalchemy.sql.expression import Insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app import scheduler
from app.db import GetDB
from app.db.models import Admin, Node, NodeUsage, NodeUserUsage, System, User
from app.node import node_manager as node_manager
from app.utils.logger import get_logger
from config import (
    DISABLE_RECORDING_NODE_USAGE,
    JOB_RECORD_NODE_USAGES_INTERVAL,
    JOB_RECORD_USER_USAGES_INTERVAL,
)

logger = get_logger("record-usages")


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


async def safe_execute(stmt, params=None, max_retries: int = 5):
    """
    Safely execute database operations with deadlock and connection handling.
    Creates a fresh DB session for each retry attempt to release locks.

    Args:
        stmt: SQLAlchemy statement to execute
        params (list[dict], optional): Parameters for the statement
        max_retries (int, optional): Maximum number of retry attempts (default: 5)
    """
    for attempt in range(max_retries):
        try:
            # Create fresh session for each attempt to release any locks from previous attempts
            async with GetDB() as db:
                dialect = db.bind.dialect.name

                # MySQL-specific IGNORE prefix - but skip if using ON DUPLICATE KEY UPDATE
                if dialect == "mysql" and isinstance(stmt, Insert):
                    # Check if statement already has ON DUPLICATE KEY UPDATE
                    if not hasattr(stmt, "_post_values_clause") or stmt._post_values_clause is None:
                        stmt = stmt.prefix_with("IGNORE")

                # Use raw connection to avoid ORM bulk update requirements
                await (await db.connection()).execute(stmt, params)
                await db.commit()
                return  # Success - exit function

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
                    # Exponential backoff with jitter: 50-75ms, 100-150ms, 200-300ms, 400-600ms, 800-1200ms
                    base_delay = 0.05 * (2**attempt)
                    jitter = random.uniform(0, base_delay * 0.5)
                    await asyncio.sleep(base_delay + jitter)
                    continue
                elif is_sqlite_locked:
                    await asyncio.sleep(0.1 * (attempt + 1))  # Linear backoff
                    continue

            # If we've exhausted retries or it's not a retriable error, raise
            raise


async def record_user_stats(params: list[dict], node_id: int, usage_coefficient: int = 1):
    """
    Record user statistics for a specific node using UPSERT for efficiency.

    Args:
        params (list[dict]): User statistic parameters
        node_id (int): Node identifier
        usage_coefficient (int, optional): usage multiplier
    """
    if not params:
        return

    created_at = dt.now(tz.utc).replace(minute=0, second=0, microsecond=0)

    # Get dialect without holding session
    dialect = await get_dialect()

    # Prepare parameters - ensure uid is converted to int
    upsert_params = [
        {
            "uid": int(p["uid"]),
            "value": int(p["value"] * usage_coefficient),
            "node_id": node_id,
            "created_at": created_at,
        }
        for p in params
    ]

    # Build and execute queries for the specific dialect
    queries = build_node_user_usage_upsert(dialect, upsert_params)
    for stmt, stmt_params in queries:
        await safe_execute(stmt, stmt_params)


async def record_node_stats(params: list[dict], node_id: int):
    """
    Record node-level statistics using UPSERT for efficiency.

    Args:
        params (list[dict]): Node statistic parameters
        node_id (int): Node identifier
    """
    if not params:
        return

    created_at = dt.now(tz.utc).replace(minute=0, second=0, microsecond=0)

    # Aggregate uplink and downlink from params
    total_up = sum(p.get("up", 0) for p in params)
    total_down = sum(p.get("down", 0) for p in params)

    # Get dialect without holding session
    dialect = await get_dialect()

    upsert_param = {
        "node_id": node_id,
        "created_at": created_at,
        "up": total_up,
        "down": total_down,
    }

    # Build and execute queries for the specific dialect
    queries = build_node_usage_upsert(dialect, upsert_param)
    for stmt, stmt_params in queries:
        await safe_execute(stmt, stmt_params)


async def get_users_stats(node: PasarGuardNode):
    try:
        stats_respons = await node.get_stats(stat_type=StatType.UsersStat, reset=True, timeout=30)
        params = defaultdict(int)
        for stat in filter(attrgetter("value"), stats_respons.stats):
            params[stat.name.split(".", 1)[0]] += stat.value

        # Validate UIDs and filter out invalid ones
        validated_params = []
        for uid, value in params.items():
            try:
                uid_int = int(uid)
                validated_params.append({"uid": uid_int, "value": value})
            except (ValueError, TypeError):
                # Skip invalid UIDs that can't be converted to int
                logger.warning("Skipping invalid UID: %s", uid)
                continue

        return validated_params
    except NodeAPIError as e:
        logger.error("Failed to get users stats, error: %s", e.detail)
        return []
    except Exception as e:
        logger.error("Failed to get users stats, unknown error: %s", e)
        return []


async def get_outbounds_stats(node: PasarGuardNode):
    try:
        stats_respons = await node.get_stats(stat_type=StatType.Outbounds, reset=True, timeout=10)
        params = [
            {"up": stat.value, "down": 0} if stat.type == "uplink" else {"up": 0, "down": stat.value}
            for stat in filter(attrgetter("value"), stats_respons.stats)
        ]
        return params
    except NodeAPIError as e:
        logger.error("Failed to get outbounds stats, error: %s", e.detail)
        return []
    except Exception as e:
        logger.error("Failed to get outbounds stats, unknown error: %s", e)
        return []


async def calculate_admin_usage(users_usage: list) -> dict:
    if not users_usage:
        return {}

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

    return admin_usage


async def calculate_users_usage(api_params: dict, usage_coefficient: dict) -> list:
    """Calculate aggregated user usage across all nodes with coefficients applied"""
    users_usage = defaultdict(int)

    # Process all node data in a single pass
    for node_id, params in api_params.items():
        coeff = usage_coefficient.get(node_id, 1)
        # Use generator to avoid intermediate lists
        node_usage = ((int(param["uid"]), int(param["value"] * coeff)) for param in params)
        for uid, value in node_usage:
            users_usage[uid] += value

    return [{"uid": uid, "value": value} for uid, value in users_usage.items()]


async def record_user_usages():
    nodes: tuple[int, PasarGuardNode] = await node_manager.get_healthy_nodes()

    node_data = await asyncio.gather(*[asyncio.create_task(node.get_extra()) for _, node in nodes])
    usage_coefficient = {node_id: data.get("usage_coefficient", 1) for (node_id, _), data in zip(nodes, node_data)}

    stats_tasks = [asyncio.create_task(get_users_stats(node)) for _, node in nodes]
    await asyncio.gather(*stats_tasks)

    api_params = {nodes[i][0]: task.result() for i, task in enumerate(stats_tasks)}

    users_usage = await calculate_users_usage(api_params, usage_coefficient)
    if not users_usage:
        return

    user_stmt = (
        update(User)
        .where(User.id == bindparam("uid"))
        .values(used_traffic=User.used_traffic + bindparam("value"), online_at=dt.now(tz.utc))
        .execution_options(synchronize_session=False)
    )
    await safe_execute(user_stmt, users_usage)

    admin_usage = await calculate_admin_usage(users_usage)
    if admin_usage:
        admin_data = [{"admin_id": aid, "value": val} for aid, val in admin_usage.items()]
        admin_stmt = (
            update(Admin)
            .where(Admin.id == bindparam("admin_id"))
            .values(used_traffic=Admin.used_traffic + bindparam("value"))
            .execution_options(synchronize_session=False)
        )
        await safe_execute(admin_stmt, admin_data)

    if DISABLE_RECORDING_NODE_USAGE:
        return

    record_tasks = [
        asyncio.create_task(
            record_user_stats(params=api_params[node_id], node_id=node_id, usage_coefficient=usage_coefficient[node_id])
        )
        for node_id in api_params
    ]
    await asyncio.gather(*record_tasks)


async def record_node_usages():
    # Create tasks for all nodes
    tasks = {
        node_id: asyncio.create_task(get_outbounds_stats(node))
        for node_id, node in await node_manager.get_healthy_nodes()
    }

    await asyncio.gather(*tasks.values())

    api_params = {node_id: task.result() for node_id, task in tasks.items()}

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
        return

    # Update each node's uplink/downlink
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
        await safe_execute(node_update_stmt, node_update_params)

    # Update system totals
    system_update_stmt = update(System).values(uplink=System.uplink + total_up, downlink=System.downlink + total_down)
    await safe_execute(system_update_stmt)

    if DISABLE_RECORDING_NODE_USAGE:
        return

    record_tasks = [asyncio.create_task(record_node_stats(params, node_id)) for node_id, params in api_params.items()]
    await asyncio.gather(*record_tasks)


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
