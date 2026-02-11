from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CoreConfig
from app.models.core import CoreCreate


CoreSortingOptionsSimple = Enum(
    "CoreSortingOptionsSimple",
    {
        "id": CoreConfig.id.asc(),
        "-id": CoreConfig.id.desc(),
        "name": CoreConfig.name.asc(),
        "-name": CoreConfig.name.desc(),
    },
)

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
    db_core_config = CoreConfig(
        name=core_config.name,
        config=core_config.config,
        exclude_inbound_tags=core_config.exclude_inbound_tags or set(),
        fallbacks_inbound_tags=core_config.fallbacks_inbound_tags or set(),
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


async def get_core_configs(db: AsyncSession, offset: int = None, limit: int = None) -> tuple[int, list[CoreConfig]]:
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
    query = select(CoreConfig)
    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)

    all_core_configs = (await db.execute(query)).scalars().all()
    return all_core_configs, len(all_core_configs)


async def get_cores_simple(
    db: AsyncSession,
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: list[CoreSortingOptionsSimple] | None = None,
    skip_pagination: bool = False,
) -> tuple[list[tuple[int, str]], int]:
    """
    Retrieves lightweight core data with only id and name.

    Args:
        db: Database session.
        offset: Number of records to skip.
        limit: Number of records to retrieve.
        search: Search term for core name.
        sort: Sort options.
        skip_pagination: If True, ignore offset/limit and return all records (max 1,000).

    Returns:
        Tuple of (list of (id, name) tuples, total_count).
    """
    stmt = select(CoreConfig.id, CoreConfig.name)

    if search:
        stmt = stmt.where(CoreConfig.name.ilike(f"%{search}%"))

    if sort:
        sort_list = []
        for s in sort:
            if isinstance(s.value, tuple):
                sort_list.extend(s.value)
            else:
                sort_list.append(s.value)
        stmt = stmt.order_by(*sort_list)

    # Get count BEFORE pagination (always)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    # Apply pagination or safety limit
    if not skip_pagination:
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
    else:
        stmt = stmt.limit(10000)  # Safety limit when all=true

    # Execute and return
    result = await db.execute(stmt)
    rows = result.all()

    return rows, total
