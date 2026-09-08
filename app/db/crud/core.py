from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CoreConfig, Node
from app.models.core import (
    CoreCreate,
    CoreListQuery,
    CoreSimpleListQuery,
    CoreSimpleSortField,
    CoreSimpleSortOption,
)

_REORDER_BATCH_SIZE = 10_000


def _build_core_simple_sort_clause(sort_option: CoreSimpleSortOption):
    field_map = {
        CoreSimpleSortField.id: CoreConfig.id,
        CoreSimpleSortField.core_name: CoreConfig.name,
        CoreSimpleSortField.created_at: CoreConfig.created_at,
    }
    column = field_map[sort_option.field]
    return column.desc() if sort_option.value.startswith("-") else column.asc()


async def get_core_config_by_id(db: AsyncSession, core_id: int) -> CoreConfig | None:
    """
    Retrieves a core configuration by its ID.

    Args:
        db (AsyncSession): The database session.
        core_id (int): The ID of the core configuration to retrieve.

    Returns:
        Optional[CoreConfig]: The CoreConfig object if found, None otherwise.
    """
    return (await db.execute(select(CoreConfig).where(CoreConfig.id == core_id))).unique().scalar_one_or_none()


async def create_core_config(db: AsyncSession, core_config: CoreCreate) -> CoreConfig:
    """
    Creates a new core configuration in the database.

    Args:
        db (AsyncSession): The database session.
        core_config (CoreCreate): The core configuration creation model containing core details.

    Returns:
        CoreConfig: The newly created CoreConfig object.
    """
    next_sort_order = (await db.execute(select(func.coalesce(func.max(CoreConfig.sort_order), -1) + 1))).scalar_one()
    db_core_config = CoreConfig(
        name=core_config.name,
        type=core_config.type,
        config=core_config.config,
        exclude_inbound_tags=core_config.exclude_inbound_tags or set(),
        fallbacks_inbound_tags=core_config.fallbacks_inbound_tags or set(),
        sort_order=next_sort_order,
    )
    db.add(db_core_config)
    await db.commit()
    await db.refresh(db_core_config)
    return db_core_config


async def modify_core_config(
    db: AsyncSession, db_core_config: CoreConfig, modified_core_config: CoreCreate
) -> CoreConfig:
    """
    Modifies an existing core configuration with new information.

    Args:
        db (AsyncSession): The database session.
        db_core_config (CoreConfig): The CoreConfig object to be updated.
        modified_core_config (CoreCreate): The modification model containing updated core details.

    Returns:
        CoreConfig: The updated CoreConfig object.
    """
    core_data = modified_core_config.model_dump(exclude_none=True)

    for key, value in core_data.items():
        setattr(db_core_config, key, value)

    await db.commit()
    await db.refresh(db_core_config)
    return db_core_config


async def remove_core_config(db: AsyncSession, db_core_config: CoreConfig) -> None:
    """
    Removes a core configuration from the database.

    Args:
        db (AsyncSession): The database session.
        db_core_config (CoreConfig): The CoreConfig object to be removed.
    """
    await db.delete(db_core_config)
    await db.commit()


async def get_core_configs(db: AsyncSession, query: CoreListQuery) -> tuple[list[CoreConfig], int]:
    """
    Retrieves a list of core configurations with optional pagination.

    Args:
        db (AsyncSession): The database session.
        offset (int, optional): The number of records to skip (for pagination).
        limit (int, optional): The maximum number of records to return.

    Returns:
        tuple: A tuple containing:
            - list[CoreConfig]: A list of CoreConfig objects
            - int: The total count of core configurations
    """
    stmt = select(CoreConfig).order_by(CoreConfig.sort_order.asc(), CoreConfig.id.asc())
    if query.ids:
        stmt = stmt.where(CoreConfig.id.in_(query.ids))
    if query.offset:
        stmt = stmt.offset(query.offset)
    if query.limit:
        stmt = stmt.limit(query.limit)

    all_core_configs = (await db.execute(stmt)).scalars().all()
    return all_core_configs, len(all_core_configs)


async def get_cores_simple(
    db: AsyncSession,
    query: CoreSimpleListQuery,
) -> tuple[list[tuple[int, str, str | None]], int]:
    """
    Retrieves lightweight core data with only id, name and type.

    Args:
        db: Database session.
        offset: Number of records to skip.
        limit: Number of records to retrieve.
        search: Search term for core name.
        sort: Sort options.
        skip_pagination: If True, ignore offset/limit and return all records (max 1,000).

    Returns:
        Tuple of (list of (id, name, type) tuples, total_count).
    """
    stmt = select(CoreConfig.id, CoreConfig.name, CoreConfig.type)

    if query.ids:
        stmt = stmt.where(CoreConfig.id.in_(query.ids))
    if query.search:
        stmt = stmt.where(CoreConfig.name.ilike(f"%{query.search}%"))

    if query.sort:
        sort_clauses = [_build_core_simple_sort_clause(sort_option) for sort_option in query.sort]
        sort_clauses.append(CoreConfig.id.asc())
        stmt = stmt.order_by(*sort_clauses)
    else:
        stmt = stmt.order_by(CoreConfig.sort_order.asc(), CoreConfig.id.asc())

    # Get count BEFORE pagination (always)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    # Apply pagination or safety limit
    if not query.all:
        if query.offset:
            stmt = stmt.offset(query.offset)
        if query.limit:
            stmt = stmt.limit(query.limit)
    else:
        stmt = stmt.limit(10000)  # Safety limit when all=true

    # Execute and return
    result = await db.execute(stmt)
    rows = result.all()

    return rows, total


async def reorder_core_configs(db: AsyncSession, ordered_ids: list[int]) -> bool:
    """Reorder the requested cores while preserving non-requested positions."""
    current_ids = list(
        (
            await db.execute(
                select(CoreConfig.id).order_by(CoreConfig.sort_order.asc(), CoreConfig.id.asc()).with_for_update()
            )
        ).scalars()
    )
    requested_ids = set(ordered_ids)
    if not requested_ids.issubset(current_ids):
        return False

    requested_positions = [index for index, core_id in enumerate(current_ids) if core_id in requested_ids]
    for index, core_id in zip(requested_positions, ordered_ids, strict=True):
        current_ids[index] = core_id

    for batch_start in range(0, len(current_ids), _REORDER_BATCH_SIZE):
        batch_ids = current_ids[batch_start : batch_start + _REORDER_BATCH_SIZE]
        ordering = {core_id: index for index, core_id in enumerate(batch_ids, start=batch_start)}
        await db.execute(
            update(CoreConfig)
            .where(CoreConfig.id.in_(batch_ids))
            .values(sort_order=case(ordering, value=CoreConfig.id))
        )
    await db.commit()
    return True


async def remove_cores(db: AsyncSession, core_ids: list[int]) -> None:
    """
    Removes multiple cores from the database by ID.

    Args:
        db (AsyncSession): Database session.
        core_ids (list[int]): List of core IDs to remove.
    """
    if not core_ids:
        return

    await db.execute(update(Node).where(Node.core_config_id.in_(core_ids)).values(core_config_id=None))
    await db.execute(delete(CoreConfig).where(CoreConfig.id.in_(core_ids)))
    await db.commit()
