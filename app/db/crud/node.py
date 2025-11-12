from datetime import datetime, timezone
from typing import Optional, Union

from sqlalchemy import and_, case, delete, func, select, update, bindparam
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import coalesce

from app.db.models import (
    DataLimitResetStrategy,
    Node,
    NodeStat,
    NodeStatus,
    NodeUsage,
    NodeUsageResetLogs,
    NodeUserUsage,
)
from app.db.compiles_types import DateDiff
from app.models.node import NodeCreate, NodeModify, UsageTable
from app.models.stats import NodeStats, NodeStatsList, NodeUsageStat, NodeUsageStatsList, Period

from .general import _build_trunc_expression


async def load_node_attrs(node: Node):
    try:
        await node.awaitable_attrs.usage_logs
    except AttributeError:
        pass


async def get_node(db: AsyncSession, name: str) -> Optional[Node]:
    """
    Retrieves a node by its name.

    Args:
        db (AsyncSession): The database session.
        name (str): The name of the node to retrieve.

    Returns:
        Optional[Node]: The Node object if found, None otherwise.
    """
    return (await db.execute(select(Node).where(Node.name == name))).unique().scalar_one_or_none()


async def get_node_by_id(db: AsyncSession, node_id: int) -> Optional[Node]:
    """
    Retrieves a node by its ID.

    Args:
        db (AsyncSession): The database session.
        node_id (int): The ID of the node to retrieve.

    Returns:
        Optional[Node]: The Node object if found, None otherwise.
    """
    return (await db.execute(select(Node).where(Node.id == node_id))).unique().scalar_one_or_none()


async def get_nodes(
    db: AsyncSession,
    status: Optional[Union[NodeStatus, list]] = None,
    enabled: bool | None = None,
    core_id: int | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> list[Node]:
    """
    Retrieves nodes based on optional status and enabled filters.

    Args:
        db (AsyncSession): The database session.
        status (Optional[Union[app.db.models.NodeStatus, list]]): The status or list of statuses to filter by.
        enabled (bool): If True, excludes disabled nodes.

    Returns:
        List[Node]: A list of Node objects matching the criteria.
    """
    query = select(Node)

    if status:
        if isinstance(status, list):
            query = query.where(Node.status.in_(status))
        else:
            query = query.where(Node.status == status)

    if enabled:
        query = query.where(Node.status != NodeStatus.disabled)

    if core_id:
        query = query.where(Node.core_config_id == core_id)

    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)

    return (await db.execute(query)).scalars().all()


async def get_limited_nodes(db: AsyncSession) -> list[Node]:
    """
    Retrieves nodes that have exceeded their data limit and are in
    error/connected/connecting status.

    Args:
        db (AsyncSession): The database session.

    Returns:
        list[Node]: Nodes that should be limited
    """
    query = select(Node).where(
        and_(
            Node.status.in_([NodeStatus.error, NodeStatus.connected, NodeStatus.connecting]),
            Node.is_limited,
        )
    )
    return (await db.execute(query)).scalars().all()


async def get_nodes_usage(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    period: Period,
    node_id: int | None = None,
    group_by_node: bool = False,
) -> NodeUsageStatsList:
    """
    Retrieves usage data for all nodes within a specified time range.

    Args:
        db (AsyncSession): The database session.
        start (datetime): The start time of the usage period.
        end (datetime): The end time of the usage period.

    Returns:
        NodeUsageStatsList: A NodeUsageStatsList contain list of NodeUsageResponse objects containing usage data.
    """
    trunc_expr = _build_trunc_expression(db, period, NodeUsage.created_at)

    conditions = [NodeUsage.created_at >= start, NodeUsage.created_at <= end]

    if node_id is not None:
        conditions.append(NodeUsage.node_id == node_id)
    else:
        node_id = -1  # Default value for node_id when not specified

    if group_by_node:
        stmt = (
            select(
                trunc_expr.label("period_start"),
                func.coalesce(NodeUsage.node_id, 0).label("node_id"),
                func.sum(NodeUsage.downlink).label("downlink"),
                func.sum(NodeUsage.uplink).label("uplink"),
            )
            .where(and_(*conditions))
            .group_by(trunc_expr, NodeUsage.node_id)
            .order_by(trunc_expr)
        )
    else:
        stmt = (
            select(
                trunc_expr.label("period_start"),
                func.sum(NodeUsage.downlink).label("downlink"),
                func.sum(NodeUsage.uplink).label("uplink"),
            )
            .where(and_(*conditions))
            .group_by(trunc_expr)
            .order_by(trunc_expr)
        )

    result = await db.execute(stmt)
    stats = {}
    for row in result.mappings():
        row_dict = dict(row)
        node_id_val = row_dict.pop("node_id", node_id)
        if node_id_val not in stats:
            stats[node_id_val] = []
        stats[node_id_val].append(NodeUsageStat(**row_dict))

    return NodeUsageStatsList(period=period, start=start, end=end, stats=stats)


async def get_node_stats(
    db: AsyncSession, node_id: int, start: datetime, end: datetime, period: Period
) -> NodeStatsList:
    trunc_expr = _build_trunc_expression(db, period, NodeStat.created_at)
    conditions = [NodeStat.created_at >= start, NodeStat.created_at <= end, NodeStat.node_id == node_id]

    stmt = (
        select(
            trunc_expr.label("period_start"),
            func.avg(NodeStat.mem_used / NodeStat.mem_total * 100).label("mem_usage_percentage"),
            func.avg(NodeStat.cpu_usage).label("cpu_usage_percentage"),  # CPU usage is already in percentage
            func.avg(NodeStat.incoming_bandwidth_speed).label("incoming_bandwidth_speed"),
            func.avg(NodeStat.outgoing_bandwidth_speed).label("outgoing_bandwidth_speed"),
        )
        .where(and_(*conditions))
        .group_by(trunc_expr)
        .order_by(trunc_expr)
    )

    result = await db.execute(stmt)

    return NodeStatsList(period=period, start=start, end=end, stats=[NodeStats(**row) for row in result.mappings()])


async def create_node(db: AsyncSession, node: NodeCreate) -> Node:
    """
    Creates a new node in the database.

    Args:
        db (AsyncSession): The database session.
        node (NodeCreate): The node creation model containing node details.

    Returns:
        Node: The newly created Node object.
    """
    db_node = Node(**node.model_dump())

    db.add(db_node)
    await db.commit()
    await db.refresh(db_node)
    return db_node


async def remove_node(db: AsyncSession, db_node: Node) -> Node:
    """
    Removes a node from the database.

    Args:
        db (AsyncSession): The database session.
        dbnode (Node): The Node object to be removed.

    Returns:
        Node: The removed Node object.
    """
    await db.delete(db_node)
    await db.commit()


async def modify_node(db: AsyncSession, db_node: Node, modify: NodeModify) -> Node:
    """
    modify an existing node with new information.

    Args:
        db (AsyncSession): The database session.
        dbnode (Node): The Node object to be updated.
        modify (NodeModify): The modification model containing updated node details.

    Returns:
        Node: The modified Node object.
    """

    node_data = modify.model_dump(exclude_none=True)

    for key, value in node_data.items():
        setattr(db_node, key, value)

    db_node.xray_version = None
    db_node.message = None
    db_node.node_version = None

    if db_node.status == NodeStatus.limited and db_node.data_limit > db_node.used_traffic:
        db_node.status = NodeStatus.connecting
    elif db_node.status not in (NodeStatus.disabled, NodeStatus.limited):
        db_node.status = NodeStatus.connecting

    await db.commit()
    await db.refresh(db_node)
    return db_node


async def update_node_status(
    db: AsyncSession,
    db_node: Node,
    status: NodeStatus,
    message: str = "",
    xray_version: str = "",
    node_version: str = "",
) -> Node:
    """
    Updates the status of a node.

    Args:
        db (AsyncSession): The database session.
        dbnode (Node): The Node object to be updated.
        status (app.db.models.NodeStatus): The new status of the node.
        message (str, optional): A message associated with the status update.
        version (str, optional): The version of the node software.

    Returns:
        Node: The updated Node object.
    """
    stmt = (
        update(Node)
        .where(Node.id == db_node.id)
        .values(
            status=status,
            message=message,
            xray_version=xray_version,
            node_version=node_version,
            last_status_change=datetime.now(timezone.utc),
        )
    )
    await db.execute(stmt)
    await db.commit()
    await db.refresh(db_node)
    return db_node


def _table_model(table: UsageTable):
    if table == UsageTable.node_user_usages:
        return NodeUserUsage
    if table == UsageTable.node_usages:
        return NodeUsage
    raise ValueError("Invalid table enum")


async def bulk_update_node_status(
    db: AsyncSession,
    updates: list[dict],
) -> None:
    """
    Update multiple node statuses in a single query using bindparam.

    Args:
        db (AsyncSession): The database session.
        updates (list[dict]): List of updates with keys: node_id, status, message, xray_version, node_version.

    Example:
        updates = [
            {"node_id": 1, "status": NodeStatus.connected, "message": "", "xray_version": "1.8.0", "node_version": "0.1.0"},
            {"node_id": 2, "status": NodeStatus.error, "message": "Connection failed", "xray_version": "", "node_version": ""},
        ]
    """
    if not updates:
        return

    stmt = (
        update(Node)
        .where(Node.id == bindparam("node_id"))
        .values(
            status=bindparam("status"),
            message=bindparam("message"),
            xray_version=bindparam("xray_version"),
            node_version=bindparam("node_version"),
            last_status_change=bindparam("now"),
        )
    )

    # Add timestamp to each update
    now = datetime.now(timezone.utc)
    for upd in updates:
        upd["now"] = now

    # Execute using connection-level execute (bypasses ORM, allows bindparam with WHERE)
    conn = await db.connection()
    await conn.execute(stmt, updates)
    await db.commit()


async def clear_usage_data(
    db: AsyncSession, table: UsageTable, start: datetime | None = None, end: datetime | None = None
):
    filters = []
    if start:
        filters.append(getattr(_table_model(table), "created_at") >= start.replace(tzinfo=timezone.utc))
    if end:
        filters.append(getattr(_table_model(table), "created_at") < end.replace(tzinfo=timezone.utc))

    stmt = delete(_table_model(table))
    if filters:
        stmt = stmt.where(and_(*filters))

    await db.execute(stmt)
    await db.commit()


async def get_nodes_to_reset_usage(db: AsyncSession) -> list[Node]:
    """
    Retrieves nodes whose usage needs to be reset based on their reset strategy and reset_time.
    For reset_time == -1: Uses interval-based calculation (days since last reset)
    For reset_time >= 0: Uses absolute time calculation based on strategy
    """
    last_reset_subq = (
        select(
            NodeUsageResetLogs.node_id,
            func.max(NodeUsageResetLogs.created_at).label("last_reset_at"),
        )
        .group_by(NodeUsageResetLogs.node_id)
        .subquery()
    )

    last_reset_time = coalesce(last_reset_subq.c.last_reset_at, Node.created_at)

    # For reset_time == -1: interval-based reset (similar to users)
    reset_strategy_to_days = {
        DataLimitResetStrategy.day: 1,
        DataLimitResetStrategy.week: 7,
        DataLimitResetStrategy.month: 30,
        DataLimitResetStrategy.year: 365,
    }

    num_days_to_reset_case = case(
        *((Node.data_limit_reset_strategy == strategy, days) for strategy, days in reset_strategy_to_days.items()),
        else_=None,
    )

    # For reset_time >= 0: time-based reset
    # This will be evaluated in Python after fetching candidates
    # because the calculation is complex (encoded time values)

    stmt = (
        select(Node)
        .outerjoin(last_reset_subq, Node.id == last_reset_subq.c.node_id)
        .where(
            Node.status.in_([NodeStatus.connected, NodeStatus.limited, NodeStatus.error, NodeStatus.connecting]),
            Node.data_limit_reset_strategy != DataLimitResetStrategy.no_reset,
            # For interval-based (-1), check if enough days have passed
            # For time-based (>=0), we'll filter in Python
            case(
                (Node.reset_time == -1, DateDiff(func.now(), last_reset_time) >= num_days_to_reset_case),
                else_=True,  # For time-based, fetch all candidates and filter in Python
            ),
        )
    )

    nodes = list((await db.execute(stmt)).unique().scalars().all())

    # Load node attributes to avoid greenlet errors
    for node in nodes:
        await load_node_attrs(node)

    # For nodes with reset_time >= 0, filter based on absolute time

    filtered_nodes = []
    for node in nodes:
        if node.reset_time == -1:
            # Already filtered by SQL query
            filtered_nodes.append(node)
        else:
            # Time-based reset: check if current time matches the schedule
            now = datetime.now(timezone.utc)

            # Get last reset time
            if node.usage_logs:
                last_reset = max(log.created_at for log in node.usage_logs)
            else:
                last_reset = node.created_at

            should_reset = False

            if node.data_limit_reset_strategy == DataLimitResetStrategy.day:
                # reset_time is seconds of day (0-86400)
                current_seconds = now.hour * 3600 + now.minute * 60 + now.second
                last_reset_seconds = last_reset.hour * 3600 + last_reset.minute * 60 + last_reset.second

                # Reset if we've passed the reset_time today and last reset was before today's reset time
                if current_seconds >= node.reset_time and (
                    now.date() > last_reset.date() or last_reset_seconds < node.reset_time
                ):
                    should_reset = True

            elif node.data_limit_reset_strategy == DataLimitResetStrategy.week:
                # reset_time is day_of_week * 86400 + seconds (0-604800)
                target_day = node.reset_time // 86400
                target_seconds = node.reset_time % 86400

                current_day = now.weekday()
                current_seconds = now.hour * 3600 + now.minute * 60 + now.second
                current_week_seconds = current_day * 86400 + current_seconds

                last_reset_day = last_reset.weekday()
                last_reset_seconds = last_reset.hour * 3600 + last_reset.minute * 60 + last_reset.second
                last_reset_week_seconds = last_reset_day * 86400 + last_reset_seconds

                # Check if enough time has passed (at least 7 days) and we're past the target time
                days_diff = (now.date() - last_reset.date()).days
                if (
                    days_diff >= 7
                    and current_week_seconds >= node.reset_time
                    and (last_reset_week_seconds < node.reset_time or days_diff > 7)
                ):
                    should_reset = True

            elif node.data_limit_reset_strategy == DataLimitResetStrategy.month:
                # reset_time is day_of_month * 86400 + seconds
                target_day = min(node.reset_time // 86400, 28)  # Max day 28 to handle all months
                target_seconds = node.reset_time % 86400

                current_day = now.day
                current_seconds = now.hour * 3600 + now.minute * 60 + now.second

                # Check if we're past the target day and time in current month
                # and last reset was before this month's target time
                if current_day > target_day or (current_day == target_day and current_seconds >= target_seconds):
                    # Check if last reset was in a previous month or before target time this month
                    if (
                        now.year > last_reset.year
                        or now.month > last_reset.month
                        or (
                            now.month == last_reset.month
                            and (
                                last_reset.day < target_day
                                or (
                                    last_reset.day == target_day
                                    and last_reset.hour * 3600 + last_reset.minute * 60 + last_reset.second
                                    < target_seconds
                                )
                            )
                        )
                    ):
                        should_reset = True

            elif node.data_limit_reset_strategy == DataLimitResetStrategy.year:
                # reset_time is day_of_year * 86400 + seconds
                target_day_of_year = node.reset_time // 86400
                target_seconds = node.reset_time % 86400

                current_day_of_year = now.timetuple().tm_yday
                current_seconds = now.hour * 3600 + now.minute * 60 + now.second

                last_reset_day_of_year = last_reset.timetuple().tm_yday

                # Check if we're past the target day in current year
                # and last reset was before this year's target time
                if current_day_of_year > target_day_of_year or (
                    current_day_of_year == target_day_of_year and current_seconds >= target_seconds
                ):
                    if now.year > last_reset.year or (
                        now.year == last_reset.year and last_reset_day_of_year < target_day_of_year
                    ):
                        should_reset = True

            if should_reset:
                filtered_nodes.append(node)

    return filtered_nodes


async def reset_node_usage(db: AsyncSession, db_node: Node) -> Node:
    """
    Resets the usage data for a node and logs the reset.

    Args:
        db (AsyncSession): Database session.
        db_node (Node): The node object whose usage is to be reset.

    Returns:
        Node: The updated node object.
    """
    # Create usage log entry with current uplink and downlink
    usage_log = NodeUsageResetLogs(
        node_id=db_node.id,
        uplink=db_node.uplink,
        downlink=db_node.downlink,
    )
    db.add(usage_log)

    # Reset node usage to zero
    db_node.uplink = 0
    db_node.downlink = 0

    if db_node.status is NodeStatus.limited:
        db_node.status = NodeStatus.connecting

    await db.commit()
    await db.refresh(db_node)
    await load_node_attrs(db_node)
    return db_node


async def bulk_reset_node_usage(db: AsyncSession, nodes: list[Node]) -> list[Node]:
    """
    Resets the usage data for a list of nodes and logs the resets.

    Args:
        db (AsyncSession): Database session.
        nodes (list[Node]): The list of node objects whose usage is to be reset.

    Returns:
        list[Node]: The updated list of node objects.
    """
    for db_node in nodes:
        # Create usage log entry
        usage_log = NodeUsageResetLogs(
            node_id=db_node.id,
            uplink=db_node.uplink,
            downlink=db_node.downlink,
        )
        db.add(usage_log)

        # Reset usage to zero
        db_node.uplink = 0
        db_node.downlink = 0

        # Update status if was limited
        if db_node.status == NodeStatus.limited:
            db_node.status = NodeStatus.connecting

    await db.commit()
    for node in nodes:
        await db.refresh(node)
        await load_node_attrs(node)
    return nodes
