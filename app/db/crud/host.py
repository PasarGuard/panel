import asyncio
from typing import List

from sqlalchemy import bindparam, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import HostTag, ProxyHost, ProxyInbound, hosts_tags_association
from app.models.host import CreateHost, HostListQuery, HostTagCreate, HostTagModify


async def resolve_host_tags(db: AsyncSession, tag_ids: list[int]) -> list[HostTag]:
    """Resolve a list of tag ids to HostTag rows, preserving the requested order."""
    if not tag_ids:
        return []
    unique_ids = list(dict.fromkeys(tag_ids))
    result = await db.execute(select(HostTag).where(HostTag.id.in_(unique_ids)))
    by_id = {tag.id: tag for tag in result.scalars().all()}
    return [by_id[tag_id] for tag_id in unique_ids if tag_id in by_id]


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


async def get_hosts(db: AsyncSession, query: HostListQuery | None = None) -> list[ProxyHost]:
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
    query = query or HostListQuery()
    stmt = select(ProxyHost).options(selectinload(ProxyHost.tags)).order_by(ProxyHost.priority.asc())

    if query.ids:
        stmt = stmt.where(ProxyHost.id.in_(query.ids))
    if query.offset:
        stmt = stmt.offset(query.offset)
    if query.limit:
        stmt = stmt.limit(query.limit)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_host_by_id(db: AsyncSession, id: int) -> ProxyHost:
    """
    Retrieves host by id.

    Args:
        db (AsyncSession): Database session.
        id (int): The ID of the host.

    Returns:
        ProxyHost: The host if found.
    """
    stmt = select(ProxyHost).options(selectinload(ProxyHost.tags)).where(ProxyHost.id == id)
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
    db_host = ProxyHost(**new_host.model_dump(exclude={"inbound_tag", "id", "tags", "tag_ids"}))
    db_host.inbound = await get_or_create_inbound(db, new_host.inbound_tag)
    db_host.tags = await resolve_host_tags(db, new_host.tag_ids)

    db.add(db_host)
    await db.commit()
    return await get_host_by_id(db, db_host.id)


async def modify_host(db: AsyncSession, db_host: ProxyHost, modified_host: CreateHost) -> ProxyHost:
    host_data = modified_host.model_dump(exclude={"id", "inbound_tag", "tags", "tag_ids"})

    for key, value in host_data.items():
        setattr(db_host, key, value)

    if not modified_host.inbound_tag:
        db_host.inbound = None
    else:
        db_host.inbound = await get_or_create_inbound(db, modified_host.inbound_tag)

    db_host.tags = await resolve_host_tags(db, modified_host.tag_ids)

    await db.commit()
    return await get_host_by_id(db, db_host.id)


async def get_host_tags(db: AsyncSession) -> list[HostTag]:
    """Return all host tags ordered by name."""
    result = await db.execute(select(HostTag).order_by(HostTag.name.asc()))
    return list(result.scalars().all())


async def get_host_tag_by_id(db: AsyncSession, id: int) -> HostTag | None:
    result = await db.execute(select(HostTag).where(HostTag.id == id))
    return result.scalar_one_or_none()


async def get_host_tag_by_name(db: AsyncSession, name: str) -> HostTag | None:
    result = await db.execute(select(HostTag).where(HostTag.name == name))
    return result.scalar_one_or_none()


async def create_host_tag(db: AsyncSession, new_tag: HostTagCreate) -> HostTag:
    db_tag = HostTag(name=new_tag.name, color=new_tag.color.value)
    db.add(db_tag)
    await db.commit()
    await db.refresh(db_tag)
    return db_tag


async def modify_host_tag(db: AsyncSession, db_tag: HostTag, modified_tag: HostTagModify) -> HostTag:
    if modified_tag.name is not None:
        db_tag.name = modified_tag.name
    if modified_tag.color is not None:
        db_tag.color = modified_tag.color.value
    await db.commit()
    await db.refresh(db_tag)
    return db_tag


async def remove_host_tag(db: AsyncSession, db_tag: HostTag) -> None:
    await db.delete(db_tag)
    await db.commit()


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


async def remove_hosts(db: AsyncSession, host_ids: list[int]) -> None:
    """
    Removes multiple hosts from the database by ID.

    Args:
        db (AsyncSession): Database session.
        host_ids (list[int]): List of host IDs to remove.
    """
    if not host_ids:
        return

    await db.execute(delete(hosts_tags_association).where(hosts_tags_association.c.host_id.in_(host_ids)))
    await db.execute(delete(ProxyHost).where(ProxyHost.id.in_(host_ids)))
    await db.commit()
