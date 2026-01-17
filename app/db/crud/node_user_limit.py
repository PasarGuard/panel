from typing import Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NodeUserLimit, NodeUserUsage
from app.models.node_user_limit import NodeUserLimitCreate


async def get_node_user_limit(
    db: AsyncSession, user_id: int, node_id: int
) -> Optional[NodeUserLimit]:
    """
    Retrieves a specific node user limit by user_id and node_id.

    Args:
        db (AsyncSession): The database session.
        user_id (int): The user ID.
        node_id (int): The node ID.

    Returns:
        Optional[NodeUserLimit]: The NodeUserLimit object if found, None otherwise.
    """
    stmt = select(NodeUserLimit).where(
        and_(NodeUserLimit.user_id == user_id, NodeUserLimit.node_id == node_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_node_user_limit_by_id(db: AsyncSession, limit_id: int) -> Optional[NodeUserLimit]:
    """
    Retrieves a node user limit by its ID.

    Args:
        db (AsyncSession): The database session.
        limit_id (int): The limit ID.

    Returns:
        Optional[NodeUserLimit]: The NodeUserLimit object if found, None otherwise.
    """
    stmt = select(NodeUserLimit).where(NodeUserLimit.id == limit_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_user_limits_for_node(db: AsyncSession, node_id: int) -> list[NodeUserLimit]:
    """
    Retrieves all user limits for a specific node.

    Args:
        db (AsyncSession): The database session.
        node_id (int): The node ID.

    Returns:
        list[NodeUserLimit]: List of NodeUserLimit objects for the node.
    """
    stmt = select(NodeUserLimit).where(NodeUserLimit.node_id == node_id)
    return list((await db.execute(stmt)).scalars().all())


async def get_node_limits_for_user(db: AsyncSession, user_id: int) -> list[NodeUserLimit]:
    """
    Retrieves all node limits for a specific user.

    Args:
        db (AsyncSession): The database session.
        user_id (int): The user ID.

    Returns:
        list[NodeUserLimit]: List of NodeUserLimit objects for the user.
    """
    stmt = select(NodeUserLimit).where(NodeUserLimit.user_id == user_id)
    return list((await db.execute(stmt)).scalars().all())


async def create_node_user_limit(
    db: AsyncSession, limit: NodeUserLimitCreate
) -> NodeUserLimit:
    """
    Creates a new node user limit.

    Args:
        db (AsyncSession): The database session.
        limit (NodeUserLimitCreate): The limit creation model.

    Returns:
        NodeUserLimit: The newly created NodeUserLimit object.
    """
    db_limit = NodeUserLimit(**limit.model_dump())
    db.add(db_limit)
    await db.commit()
    await db.refresh(db_limit)
    return db_limit


async def upsert_node_user_limit(
    db: AsyncSession, limit: NodeUserLimitCreate
) -> NodeUserLimit:
    """
    Creates or updates a node user limit (upsert).
    If limit exists for user_id/node_id, updates it; otherwise creates new.

    Args:
        db (AsyncSession): The database session.
        limit (NodeUserLimitCreate): The limit data.

    Returns:
        NodeUserLimit: The created or updated NodeUserLimit object.
    """
    existing = await get_node_user_limit(db, limit.user_id, limit.node_id)
    
    if existing:
        existing.data_limit = limit.data_limit
        existing.data_limit_reset_strategy = limit.data_limit_reset_strategy
        existing.reset_time = limit.reset_time
        await db.commit()
        await db.refresh(existing)
        return existing
    else:
        return await create_node_user_limit(db, limit)


async def modify_node_user_limit(
    db: AsyncSession, db_limit: NodeUserLimit, data_limit: int, 
    data_limit_reset_strategy: str | None = None, reset_time: int | None = None
) -> NodeUserLimit:
    """
    Modifies an existing node user limit.

    Args:
        db (AsyncSession): The database session.
        db_limit (NodeUserLimit): The NodeUserLimit object to modify.
        data_limit (int): The new data limit value.
        data_limit_reset_strategy (str | None): The reset strategy.
        reset_time (int | None): The reset time.

    Returns:
        NodeUserLimit: The modified NodeUserLimit object.
    """
    db_limit.data_limit = data_limit
    if data_limit_reset_strategy is not None:
        db_limit.data_limit_reset_strategy = data_limit_reset_strategy
    if reset_time is not None:
        db_limit.reset_time = reset_time
    await db.commit()
    await db.refresh(db_limit)
    return db_limit


async def remove_node_user_limit(db: AsyncSession, db_limit: NodeUserLimit) -> None:
    """
    Removes a node user limit.

    Args:
        db (AsyncSession): The database session.
        db_limit (NodeUserLimit): The NodeUserLimit object to remove.
    """
    await db.execute(delete(NodeUserLimit).where(NodeUserLimit.id == db_limit.id))
    await db.commit()


async def bulk_set_user_limits_for_node(
    db: AsyncSession, node_id: int, user_limits: dict[int, int],
    data_limit_reset_strategy: str = "no_reset", reset_time: int = -1
) -> list[NodeUserLimit]:
    """
    Bulk sets or updates user limits for a specific node.

    Args:
        db (AsyncSession): The database session.
        node_id (int): The node ID.
        user_limits (dict[int, int]): Dictionary mapping user_id to data_limit.
        data_limit_reset_strategy (str): Reset strategy to apply to all limits.
        reset_time (int): Reset time to apply to all limits.

    Returns:
        list[NodeUserLimit]: List of created/updated NodeUserLimit objects.
    """
    result_limits = []

    for user_id, data_limit in user_limits.items():
        # Check if limit already exists
        existing_limit = await get_node_user_limit(db, user_id, node_id)

        if existing_limit:
            # Update existing limit
            existing_limit.data_limit = data_limit
            existing_limit.data_limit_reset_strategy = data_limit_reset_strategy
            existing_limit.reset_time = reset_time
            result_limits.append(existing_limit)
        else:
            # Create new limit
            new_limit = NodeUserLimit(
                user_id=user_id, 
                node_id=node_id, 
                data_limit=data_limit,
                data_limit_reset_strategy=data_limit_reset_strategy,
                reset_time=reset_time
            )
            db.add(new_limit)
            result_limits.append(new_limit)

    await db.commit()

    # Refresh all limits
    for limit in result_limits:
        await db.refresh(limit)

    return result_limits
async def get_nodes_with_over_limit_users(db: AsyncSession) -> list[int]:
    """
    Finds IDs of nodes that have at least one user who exceeded their per-node limit.

    Args:
        db (AsyncSession): The database session.

    Returns:
        list[int]: List of node IDs.
    """
    from sqlalchemy import func

    stmt = (
        select(NodeUserLimit.node_id)
        .join(
            NodeUserUsage,
            and_(
                NodeUserLimit.user_id == NodeUserUsage.user_id,
                NodeUserLimit.node_id == NodeUserUsage.node_id,
            ),
        )
        .where(NodeUserLimit.data_limit > 0)
        .group_by(NodeUserLimit.node_id, NodeUserLimit.user_id, NodeUserLimit.data_limit)
        .having(func.sum(NodeUserUsage.used_traffic) >= NodeUserLimit.data_limit)
        .distinct()
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
