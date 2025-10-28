from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Group, ProxyInbound
from app.models.group import GroupCreate, GroupModify

from .host import upsert_inbounds


async def get_inbounds_by_tags(db: AsyncSession, tags: list[str]) -> list[ProxyInbound]:
    """
    Retrieves or creates inbounds by their tags using efficient bulk upsert.
    """
    inbounds_map = await upsert_inbounds(db, tags)
    # Return in the same order as input tags
    return [inbounds_map[tag] for tag in tags]


def get_group_query():
    return select(Group).options(
        selectinload(Group.users),
        selectinload(Group.inbounds),
        selectinload(Group.templates),
    )


async def get_group_by_id(db: AsyncSession, group_id: int) -> Group | None:
    """
    Retrieves a group by its ID.

    Args:
        db (AsyncSession): The database session.
        group_id (int): The ID of the group to retrieve.

    Returns:
        Optional[Group]: The Group object if found, None otherwise.
    """
    stmt = get_group_query().where(Group.id == group_id)
    return (await db.execute(stmt)).unique().scalar_one_or_none()


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
    await db.flush()
    group_id = db_group.id
    await db.commit()

    return await get_group_by_id(db, group_id)


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
    query = get_group_query()

    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)

    all_groups = (await db.execute(query)).unique().scalars().all()
    count = (await db.execute(select(func.count(Group.id)))).scalar_one()

    return all_groups, count


async def get_groups_by_ids(db: AsyncSession, group_ids: list[int]) -> list[Group]:
    """
    Retrieves a list of groups by their IDs.

    Args:
        db (AsyncSession): The database session.
        group_ids (list[int]): The IDs of the groups to retrieve.

    Returns:
        list[Group]: A list of Group objects.
    """
    if not group_ids:
        return []

    stmt = get_group_query().where(Group.id.in_(group_ids))
    return (await db.execute(stmt)).unique().scalars().all()


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

    group_id = db_group.id

    await db.commit()

    return await get_group_by_id(db, group_id)


async def remove_group(db: AsyncSession, dbgroup: Group):
    """
    Removes a group from the database.

    Args:
        db (AsyncSession): The database session.
        dbgroup (Group): The Group object to be removed.
    """
    await db.delete(dbgroup)
    await db.commit()
