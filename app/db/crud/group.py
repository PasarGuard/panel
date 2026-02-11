from enum import Enum
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProxyInbound, Group
from app.models.group import GroupCreate, GroupModify

from .host import upsert_inbounds


GroupsSortingOptionsSimple = Enum(
    "GroupsSortingOptionsSimple",
    {
        "id": Group.id.asc(),
        "-id": Group.id.desc(),
        "name": Group.name.asc(),
        "-name": Group.name.desc(),
    },
)


async def get_inbounds_by_tags(db: AsyncSession, tags: list[str]) -> list[ProxyInbound]:
    """
    Retrieves or creates inbounds by their tags using efficient bulk upsert.
    """
    inbounds_map = await upsert_inbounds(db, tags)
    # Return in the same order as input tags
    return [inbounds_map[tag] for tag in tags]


async def load_group_attrs(group: Group):
    await group.awaitable_attrs.users
    await group.awaitable_attrs.inbounds


async def get_group_by_id(db: AsyncSession, group_id: int) -> Group | None:
    """
    Retrieves a group by its ID.

    Args:
        db (AsyncSession): The database session.
        group_id (int): The ID of the group to retrieve.

    Returns:
        Optional[Group]: The Group object if found, None otherwise.
    """
    group = (await db.execute(select(Group).where(Group.id == group_id))).unique().scalar_one_or_none()
    if group:
        await load_group_attrs(group)
    return group


async def create_group(db: AsyncSession, group: GroupCreate) -> Group:
    """
    Creates a new group in the database.

    Args:
        db (AsyncSession): The database session.
        group (GroupCreate): The group creation model containing group details.

    Returns:
        Group: The newly created Group object.
    """
    db_group = Group(
        name=group.name,
        inbounds=await get_inbounds_by_tags(db, group.inbound_tags),
        is_disabled=group.is_disabled,
    )
    db.add(db_group)
    await db.commit()
    await db.refresh(db_group)
    await load_group_attrs(db_group)
    return db_group


async def get_group(db: AsyncSession, offset: int = None, limit: int = None) -> tuple[list[Group], int]:
    """
    Retrieves a list of groups with optional pagination.

    Args:
        db (AsyncSession): The database session.
        offset (int, optional): The number of records to skip (for pagination).
        limit (int, optional): The maximum number of records to return.

    Returns:
        tuple: A tuple containing:
            - list[Group]: A list of Group objects
            - int: The total count of groups
    """
    groups = select(Group)

    count_query = select(func.count()).select_from(groups.subquery())

    if offset:
        groups = groups.offset(offset)
    if limit:
        groups = groups.limit(limit)

    count = (await db.execute(count_query)).scalar_one()

    all_groups = (await db.execute(groups)).scalars().all()

    for group in all_groups:
        await load_group_attrs(group)

    return all_groups, count


async def get_groups_simple(
    db: AsyncSession,
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    sort: list[GroupsSortingOptionsSimple] | None = None,
    skip_pagination: bool = False,
) -> tuple[list[tuple[int, str]], int]:
    """
    Retrieves lightweight group data with only id and name.

    Args:
        db: Database session.
        offset: Number of records to skip.
        limit: Number of records to retrieve.
        search: Search term for group name.
        sort: Sort options.
        skip_pagination: If True, ignore offset/limit and return all records (max 1,000).

    Returns:
        Tuple of (list of (id, name) tuples, total_count).
    """
    stmt = select(Group.id, Group.name)

    if search:
        stmt = stmt.where(Group.name.ilike(f"%{search}%"))

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


async def get_groups_by_ids(db: AsyncSession, group_ids: list[int]) -> list[Group]:
    """
    Retrieves a list of groups by their IDs.

    Args:
        db (AsyncSession): The database session.
        group_ids (list[int]): The IDs of the groups to retrieve.

    Returns:
        list[Group]: A list of Group objects.
    """
    groups = (await db.execute(select(Group).where(Group.id.in_(group_ids)))).scalars().all()

    for group in groups:
        await load_group_attrs(group)

    return groups


async def modify_group(db: AsyncSession, db_group: Group, modified_group: GroupModify) -> Group:
    """
    Modify an existing group with new information.

    Args:
        db (AsyncSession): The database session.
        dbgroup (Group): The Group object to be updated.
        modified_group (GroupModify): The modification model containing updated group details.

    Returns:
        Group: The updated Group object.
    """

    if modified_group.inbound_tags:
        inbounds = await get_inbounds_by_tags(db, modified_group.inbound_tags)
        db_group.inbounds = inbounds
    if db_group.name != modified_group.name:
        db_group.name = modified_group.name
    if modified_group.is_disabled is not None:
        db_group.is_disabled = modified_group.is_disabled

    await db.commit()
    await db.refresh(db_group)
    await load_group_attrs(db_group)
    return db_group


async def remove_group(db: AsyncSession, dbgroup: Group):
    """
    Removes a group from the database.

    Args:
        db (AsyncSession): The database session.
        dbgroup (Group): The Group object to be removed.
    """
    await db.delete(dbgroup)
    await db.commit()
