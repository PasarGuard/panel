import asyncio

from sqlalchemy import bindparam, delete, insert, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AdminHostOverride,
    Group,
    ProxyHost,
    ProxyInbound,
    inbounds_groups_association,
)
from app.models.host import CreateHost, HostCustomizationModify, HostListQuery


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


async def get_inbounds_not_in_tags(db: AsyncSession, excluded_tags: list[str]) -> list[ProxyInbound]:
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


async def remove_inbounds(db: AsyncSession, inbounds: list[ProxyInbound]) -> None:
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
    stmt = select(ProxyHost).order_by(ProxyHost.priority.asc())

    if query.ids is not None:
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


async def modify_hosts(db: AsyncSession, modified_hosts: list[CreateHost], db_hosts: list[ProxyHost]) -> None:
    """Apply a validated host batch without committing individual rows."""
    hosts_by_id = {host.id: host for host in db_hosts}
    inbounds = await upsert_inbounds(db, [host.inbound_tag for host in modified_hosts if host.inbound_tag])
    with db.no_autoflush:
        for host in modified_hosts:
            host_data = host.model_dump(exclude={"id", "inbound_tag"})
            db_host = hosts_by_id.get(host.id)
            if db_host is None:
                db_host = ProxyHost(**host_data)
                db.add(db_host)
            else:
                for key, value in host_data.items():
                    setattr(db_host, key, value)
            db_host.inbound = inbounds.get(host.inbound_tag)
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
    await db.execute(delete(AdminHostOverride).where(AdminHostOverride.host_id == db_host.id))
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

    await db.execute(delete(AdminHostOverride).where(AdminHostOverride.host_id.in_(host_ids)))
    await db.execute(delete(ProxyHost).where(ProxyHost.id.in_(host_ids)))
    await db.commit()


async def get_group_inbound_tags(db: AsyncSession, group_ids: list[int]) -> set[str]:
    """Return the inbound tags reachable through the given groups."""
    if not group_ids:
        return set()
    stmt = (
        select(ProxyInbound.tag)
        .join(inbounds_groups_association, ProxyInbound.id == inbounds_groups_association.c.inbound_id)
        .join(Group, Group.id == inbounds_groups_association.c.group_id)
        .where(Group.id.in_(group_ids))
    )
    return set((await db.execute(stmt)).scalars().all())


async def get_admin_host_overrides(db: AsyncSession, admin_id: int) -> dict[int, AdminHostOverride]:
    """Return an admin's host overrides keyed by host ID."""
    result = await db.execute(select(AdminHostOverride).where(AdminHostOverride.admin_id == admin_id))
    return {override.host_id: override for override in result.scalars().all()}


async def get_admin_host_override_rows(db: AsyncSession, admin_id: int) -> list[tuple[AdminHostOverride, str | None]]:
    """Return an admin's host overrides together with the inbound tag of each host."""
    stmt = (
        select(AdminHostOverride, ProxyHost.inbound_tag)
        .join(ProxyHost, ProxyHost.id == AdminHostOverride.host_id)
        .where(AdminHostOverride.admin_id == admin_id)
    )
    return [(override, inbound_tag) for override, inbound_tag in (await db.execute(stmt)).all()]


async def set_admin_host_override(
    db: AsyncSession, admin_id: int, host_id: int, override: HostCustomizationModify
) -> AdminHostOverride | None:
    """
    Store an admin's override for a host, or remove it when it no longer changes anything.

    Returns:
        AdminHostOverride | None: The stored override, or None when the host is back to its defaults.
    """
    stmt = select(AdminHostOverride).where(AdminHostOverride.admin_id == admin_id, AdminHostOverride.host_id == host_id)
    db_override = (await db.execute(stmt)).scalar_one_or_none()

    if override.remark is None and not override.is_disabled:
        if db_override is not None:
            await db.delete(db_override)
            await db.commit()
        return None

    if db_override is None:
        db_override = AdminHostOverride(admin_id=admin_id, host_id=host_id)
        db.add(db_override)
    db_override.remark = override.remark
    db_override.is_disabled = override.is_disabled
    await db.commit()
    await db.refresh(db_override)
    return db_override
