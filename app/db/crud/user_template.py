from typing import List

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NextPlan, UserTemplate, template_group_association
from app.models.user_template import (
    UserTemplateCreate,
    UserTemplateListQuery,
    UserTemplateModify,
    UserTemplateSimpleListQuery,
    UserTemplateSimpleSortField,
    UserTemplateSimpleSortOption,
)

from .group import get_groups_by_ids


def _build_user_template_simple_sort_clause(sort_option: UserTemplateSimpleSortOption):
    field_map = {
        UserTemplateSimpleSortField.id: UserTemplate.id,
        UserTemplateSimpleSortField.template_name: UserTemplate.name,
    }
    column = field_map[sort_option.field]
    return column.desc() if sort_option.value.startswith("-") else column.asc()


async def load_user_template_attrs(template: UserTemplate):
    await template.awaitable_attrs.groups


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
        hwid_limit=user_template.hwid_limit,
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
    await db.commit()
    await db.refresh(db_user_template)
    await load_user_template_attrs(db_user_template)
    return db_user_template


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
    if "hwid_limit" in modified_user_template.model_fields_set:
        db_user_template.hwid_limit = modified_user_template.hwid_limit
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

    await db.commit()
    await db.refresh(db_user_template)
    await load_user_template_attrs(db_user_template)
    return db_user_template


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
    user_template = (
        (await db.execute(select(UserTemplate).where(UserTemplate.id == user_template_id)))
        .unique()
        .scalar_one_or_none()
    )
    if user_template:
        await load_user_template_attrs(user_template)
    return user_template


async def get_user_templates(db: AsyncSession, query: UserTemplateListQuery) -> List[UserTemplate]:
    """
    Retrieves a list of user templates with optional pagination.

    Args:
        db (AsyncSession): Database session.
        offset (Union[int, None]): The number of records to skip (for pagination).
        limit (Union[int, None]): The maximum number of records to return.

    Returns:
        List[UserTemplate]: A list of user template objects.
    """
    stmt = select(UserTemplate).order_by(UserTemplate.id.asc())
    if query.ids:
        stmt = stmt.where(UserTemplate.id.in_(query.ids))
    if query.offset:
        stmt = stmt.offset(query.offset)
    if query.limit:
        stmt = stmt.limit(query.limit)

    user_templates = (await db.execute(stmt)).scalars().all()
    for template in user_templates:
        await load_user_template_attrs(template)

    return user_templates


async def get_user_templates_simple(
    db: AsyncSession,
    query: UserTemplateSimpleListQuery,
) -> tuple[list[tuple[int, str]], int]:
    """
    Retrieves lightweight user template data with only id and name.

    Args:
        db: Database session.
        offset: Number of records to skip.
        limit: Number of records to retrieve.
        search: Search term for template name.
        sort: Sort options.
        skip_pagination: If True, ignore offset/limit and return all records (max 1,000).

    Returns:
        Tuple of (list of (id, name) tuples, total_count).
    """
    stmt = select(UserTemplate.id, UserTemplate.name)

    if query.ids:
        stmt = stmt.where(UserTemplate.id.in_(query.ids))
    if query.search:
        search_value = query.search.strip()
        if search_value:
            stmt = stmt.where(UserTemplate.name.ilike(f"%{search_value}%"))

    if query.sort:
        stmt = stmt.order_by(*[_build_user_template_simple_sort_clause(sort_option) for sort_option in query.sort])
    else:
        stmt = stmt.order_by(UserTemplate.id.asc())

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

    result = await db.execute(stmt)
    rows = result.all()

    return rows, total


async def remove_user_templates(db: AsyncSession, template_ids: list[int]) -> None:
    """
    Removes multiple user templates from the database by ID.

    Args:
        db (AsyncSession): Database session.
        template_ids (list[int]): List of template IDs to remove.
    """
    if not template_ids:
        return

    await db.execute(
        delete(template_group_association).where(template_group_association.c.user_template_id.in_(template_ids))
    )
    await db.execute(update(NextPlan).where(NextPlan.user_template_id.in_(template_ids)).values(user_template_id=None))
    await db.execute(delete(UserTemplate).where(UserTemplate.id.in_(template_ids)))
    await db.commit()
