import asyncio
from enum import Enum
from typing import List, Optional

from sqlalchemy import bindparam, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProxyHost, ProxyInbound
from app.models.host import CreateHost


async def upsert_inbounds(db: AsyncSession, inbound_tags: list[str]) -> dict[str, ProxyInbound]:
    """
    Efficiently upserts multiple proxy inbounds and returns them.
    Uses INSERT ... ON CONFLICT DO NOTHING pattern to avoid unnecessary SELECT queries.

    Args:
        db (AsyncSession): Database session.
        inbound_tags (List[str]): List of inbound tags to upsert.

    Returns:
        dict[str, ProxyInbound]: Mapping of tag to ProxyInbound object.

    Note:
        This function does not commit the transaction. The caller is responsible for committing.
    """
    if not inbound_tags:
        return {}

    # Remove duplicates while preserving order
    unique_tags = list(dict.fromkeys(inbound_tags))

    dialect = db.bind.dialect.name

    # Build upsert statement based on dialect
    if dialect == "postgresql":
        stmt = pg_insert(ProxyInbound).values(tag=bindparam("tag"))
        stmt = stmt.on_conflict_do_nothing(index_elements=["tag"])
    elif dialect == "mysql":
        stmt = mysql_insert(ProxyInbound).values(tag=bindparam("tag"))
        stmt = stmt.on_duplicate_key_update(tag=ProxyInbound.tag)
    else:  # SQLite
        stmt = insert(ProxyInbound).values(tag=bindparam("tag")).prefix_with("OR IGNORE")

    # Execute upsert for all tags
    params = [{"tag": tag} for tag in unique_tags]
    await db.execute(stmt, params)
    await db.flush()  # Flush to make inserted rows visible in this transaction

    # Now select all the inbounds we just upserted
    select_stmt = select(ProxyInbound).where(ProxyInbound.tag.in_(unique_tags))
    result = await db.execute(select_stmt)
    inbounds = result.scalars().all()

    # Return as a mapping
    return {inbound.tag: inbound for inbound in inbounds}


async def get_or_create_inbound(db: AsyncSession, inbound_tag: str) -> ProxyInbound:
    """
    Retrieves or creates a proxy inbound based on the given tag.

    Note: This function is deprecated. Use upsert_inbounds() for better performance,
    especially when dealing with multiple inbounds.

    Args:
        db (AsyncSession): Database session.
        inbound_tag (str): The tag of the inbound.

    Returns:
        ProxyInbound: The retrieved or newly created proxy inbound.
    """
    result = await upsert_inbounds(db, [inbound_tag])
    return result[inbound_tag]


async def get_inbounds_not_in_tags(db: AsyncSession, excluded_tags: List[str]) -> List[ProxyInbound]:
    """
    Get all inbounds where the tag is not in the provided list of tags.

    Args:
        db: Database session
        excluded_tags: List of tags to exclude

    Returns:
        List of ProxyInbound objects not matching any tag in the list
    """
    stmt = select(ProxyInbound).where(ProxyInbound.tag.not_in(excluded_tags))
    result = await db.execute(stmt)
    return result.scalars().all()


async def remove_inbounds(db: AsyncSession, inbounds: List[ProxyInbound]) -> None:
    """
    Remove a list of inbounds from the database.

    Args:
        db: Database session
        inbounds: List of ProxyInbound objects to remove
    """
    if not inbounds:
        return

    await asyncio.gather(*[db.delete(inbound) for inbound in inbounds])
    await db.commit()


ProxyHostSortingOptions = Enum(
    "ProxyHostSortingOptions",
    {
        "priority": ProxyHost.priority.asc(),
        "id": ProxyHost.id.asc(),
        "-priority": ProxyHost.priority.desc(),
        "-id": ProxyHost.id.desc(),
    },
)


ProxyHostSortingOptionsSimple = Enum(
    "ProxyHostSortingOptionsSimple",
    {
        "id": ProxyHost.id.asc(),
        "-id": ProxyHost.id.desc(),
        "remark": ProxyHost.remark.asc(),
        "-remark": ProxyHost.remark.desc(),
        "priority": ProxyHost.priority.asc(),
        "-priority": ProxyHost.priority.desc(),
    },
)


async def get_hosts(
    db: AsyncSession,
    offset: Optional[int] = 0,
    limit: Optional[int] = 0,
    sort: ProxyHostSortingOptions = ProxyHostSortingOptions.priority,
) -> list[ProxyHost]:
    """
    Retrieves hosts sorted by priority (ascending) by default.

    Args:
        db (AsyncSession): Database session.
        offset (Optional[int]): Number of records to skip.
        limit (Optional[int]): Number of records to retrieve.
        sort (ProxyHostSortingOptions): Sorting option. Defaults to priority ascending.

    Returns:
        List[ProxyHost]: List of hosts sorted by the specified option.
    """
    stmt = select(ProxyHost).order_by(sort.value)

    if offset:
        stmt = stmt.offset(offset)
    if limit:
        stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_hosts_simple(
    db: AsyncSession,
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: list[ProxyHostSortingOptionsSimple] | None = None,
    skip_pagination: bool = False,
) -> tuple[list[tuple[int, str, set[str], int | None, str | None, int]], int]:
    """
    Retrieves lightweight host data with only id, remark, address, port, inbound_tag, priority.

    Args:
        db: Database session.
        offset: Number of records to skip.
        limit: Number of records to retrieve.
        search: Search term for remark or inbound tag.
        sort: Sort options.
        skip_pagination: If True, ignore offset/limit and return all records (max 1,000).

    Returns:
        Tuple of (list of tuples, total_count).
    """
    stmt = select(
        ProxyHost.id,
        ProxyHost.remark,
        ProxyHost.address,
        ProxyHost.port,
        ProxyHost.inbound_tag,
        ProxyHost.priority,
    )

    if search:
        search_value = search.strip()
        if search_value:
            stmt = stmt.where(
                or_(
                    ProxyHost.remark.ilike(f"%{search_value}%"),
                    ProxyHost.inbound_tag.ilike(f"%{search_value}%"),
                )
            )

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

    if not skip_pagination:
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
    else:
        stmt = stmt.limit(10000)  # Safety limit when all=true

    result = await db.execute(stmt)
    rows = result.all()

    return rows, total


async def get_host_by_id(db: AsyncSession, id: int) -> ProxyHost:
    """
    Retrieves host by id.

    Args:
        db (AsyncSession): Database session.
        id (int): The ID of the host.

    Returns:
        ProxyHost: The host if found.
    """
    stmt = select(ProxyHost).where(ProxyHost.id == id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_host(db: AsyncSession, new_host: CreateHost) -> ProxyHost:
    """
    Creates a proxy Host based on the host.

    Args:
        db (AsyncSession): Database session.
        host (CreateHost): The new host to add.

    Returns:
        ProxyHost: The retrieved or newly created proxy host.
    """
    db_host = ProxyHost(**new_host.model_dump(exclude={"inbound_tag", "id"}))
    db_host.inbound = await get_or_create_inbound(db, new_host.inbound_tag)

    db.add(db_host)
    await db.commit()
    await db.refresh(db_host)
    return db_host


async def modify_host(db: AsyncSession, db_host: ProxyHost, modified_host: CreateHost) -> ProxyHost:
    host_data = modified_host.model_dump(exclude={"id", "inbound_tag"})

    for key, value in host_data.items():
        setattr(db_host, key, value)

    if not modified_host.inbound_tag:
        db_host.inbound = None
    else:
        db_host.inbound = await get_or_create_inbound(db, modified_host.inbound_tag)

    await db.commit()
    await db.refresh(db_host)
    return db_host


async def remove_host(db: AsyncSession, db_host: ProxyHost) -> ProxyHost:
    """
    Removes a proxy Host from the database.

    Args:
        db (AsyncSession): Database session.
        db_host (ProxyHost): The host to remove.

    Returns:
        ProxyHost: The removed proxy host.
    """
    await db.delete(db_host)
    await db.commit()
    return db_host
