from typing import List, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import UserTemplate
from app.models.user_template import UserTemplateCreate, UserTemplateModify

from .group import get_groups_by_ids


def get_user_template_query():
    return select(UserTemplate).options(selectinload(UserTemplate.groups))


async def create_user_template(db: AsyncSession, user_template: UserTemplateCreate) -> UserTemplate:
    """
    Creates a new user template in the database.

    Args:
        db (AsyncSession): Database session.
        user_template (UserTemplateCreate): The user template creation data.

    Returns:
        UserTemplate: The created user template object.
    """

    db_user_template = UserTemplate(
        name=user_template.name,
        data_limit=user_template.data_limit,
        expire_duration=user_template.expire_duration,
        username_prefix=user_template.username_prefix,
        username_suffix=user_template.username_suffix,
        groups=await get_groups_by_ids(db, user_template.group_ids) if user_template.group_ids else None,
        extra_settings=user_template.extra_settings.dict() if user_template.extra_settings else None,
        status=user_template.status,
        reset_usages=user_template.reset_usages,
        on_hold_timeout=user_template.on_hold_timeout,
        is_disabled=user_template.is_disabled,
        data_limit_reset_strategy=user_template.data_limit_reset_strategy,
    )

    db.add(db_user_template)
    await db.flush()
    template_id = db_user_template.id
    await db.commit()

    return await get_user_template(db, template_id)


async def modify_user_template(
    db: AsyncSession, db_user_template: UserTemplate, modified_user_template: UserTemplateModify
) -> UserTemplate:
    """
    Updates a user template's details.

    Args:
        db (AsyncSession): Database session.
        db_user_template (UserTemplate): The user template object to be updated.
        modified_user_template (UserTemplateModify): The modified user template data.

    Returns:
        UserTemplate: The updated user template object.
    """
    if modified_user_template.name is not None:
        db_user_template.name = modified_user_template.name
    if modified_user_template.data_limit is not None:
        db_user_template.data_limit = modified_user_template.data_limit
    if modified_user_template.expire_duration is not None:
        db_user_template.expire_duration = modified_user_template.expire_duration
    if modified_user_template.username_prefix is not None:
        db_user_template.username_prefix = modified_user_template.username_prefix
    if modified_user_template.username_suffix is not None:
        db_user_template.username_suffix = modified_user_template.username_suffix
    if modified_user_template.group_ids:
        db_user_template.groups = await get_groups_by_ids(db, modified_user_template.group_ids)
    if modified_user_template.extra_settings is not None:
        db_user_template.extra_settings = modified_user_template.extra_settings.dict()
    if modified_user_template.status is not None:
        db_user_template.status = modified_user_template.status
    if modified_user_template.reset_usages is not None:
        db_user_template.reset_usages = modified_user_template.reset_usages
    if modified_user_template.on_hold_timeout is not None:
        db_user_template.on_hold_timeout = modified_user_template.on_hold_timeout
    if modified_user_template.is_disabled is not None:
        db_user_template.is_disabled = modified_user_template.is_disabled
    if modified_user_template.data_limit_reset_strategy is not None:
        db_user_template.data_limit_reset_strategy = modified_user_template.data_limit_reset_strategy

    template_id = db_user_template.id

    await db.commit()

    return await get_user_template(db, template_id)


async def remove_user_template(db: AsyncSession, db_user_template: UserTemplate):
    """
    Removes a user template from the database.

    Args:
        db (AsyncSession): Database session.
        db_user_template (UserTemplate): The user template object to be removed.
    """
    await db.delete(db_user_template)
    await db.commit()


async def get_user_template(db: AsyncSession, user_template_id: int) -> UserTemplate:
    """
    Retrieves a user template by its ID.

    Args:
        db (AsyncSession): Database session.
        user_template_id (int): The ID of the user template.

    Returns:
        UserTemplate: The user template object.
    """
    stmt = get_user_template_query().where(UserTemplate.id == user_template_id)
    return (await db.execute(stmt)).unique().scalar_one_or_none()


async def get_user_templates(
    db: AsyncSession, offset: Union[int, None] = None, limit: Union[int, None] = None
) -> List[UserTemplate]:
    """
    Retrieves a list of user templates with optional pagination.

    Args:
        db (AsyncSession): Database session.
        offset (Union[int, None]): The number of records to skip (for pagination).
        limit (Union[int, None]): The maximum number of records to return.

    Returns:
        List[UserTemplate]: A list of user template objects.
    """
    query = get_user_template_query()
    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)

    return (await db.execute(query)).unique().scalars().all()
