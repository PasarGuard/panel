from collections import defaultdict
from collections.abc import Mapping
from enum import Enum

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CoreTemplate
from app.models.core_template import CoreTemplateCreate, CoreTemplateModify, CoreTemplateType
from app.subscription.default_templates import DEFAULT_TEMPLATE_CONTENTS_BY_LEGACY_KEY

TEMPLATE_TYPE_TO_LEGACY_KEY: dict[CoreTemplateType, str] = {
    CoreTemplateType.clash_subscription: "CLASH_SUBSCRIPTION_TEMPLATE",
    CoreTemplateType.xray_subscription: "XRAY_SUBSCRIPTION_TEMPLATE",
    CoreTemplateType.singbox_subscription: "SINGBOX_SUBSCRIPTION_TEMPLATE",
    CoreTemplateType.user_agent: "USER_AGENT_TEMPLATE",
    CoreTemplateType.grpc_user_agent: "GRPC_USER_AGENT_TEMPLATE",
}

CoreTemplateSortingOptionsSimple = Enum(
    "CoreTemplateSortingOptionsSimple",
    {
        "id": CoreTemplate.id.asc(),
        "-id": CoreTemplate.id.desc(),
        "name": CoreTemplate.name.asc(),
        "-name": CoreTemplate.name.desc(),
        "type": CoreTemplate.template_type.asc(),
        "-type": CoreTemplate.template_type.desc(),
    },
)


def get_default_core_template_contents() -> dict[str, str]:
    return DEFAULT_TEMPLATE_CONTENTS_BY_LEGACY_KEY.copy()


def merge_core_template_values(values: Mapping[str, str] | None = None) -> dict[str, str]:
    merged = get_default_core_template_contents()
    if not values:
        return merged

    for key, value in values.items():
        if key in merged and value:
            merged[key] = value

    return merged


async def get_core_template_values(db: AsyncSession) -> dict[str, str]:
    defaults = get_default_core_template_contents()
    try:
        rows = (
            await db.execute(
                select(
                    CoreTemplate.id,
                    CoreTemplate.template_type,
                    CoreTemplate.content,
                    CoreTemplate.is_default,
                ).order_by(CoreTemplate.template_type.asc(), CoreTemplate.id.asc())
            )
        ).all()
    except SQLAlchemyError:
        return defaults

    by_type: dict[str, list[tuple[int, str, bool]]] = defaultdict(list)
    for row in rows:
        by_type[row.template_type].append((row.id, row.content, row.is_default))

    values: dict[str, str] = {}
    for template_type, legacy_key in TEMPLATE_TYPE_TO_LEGACY_KEY.items():
        type_rows = by_type.get(template_type.value, [])
        if not type_rows:
            continue

        selected_content = ""
        for _, content, is_default in type_rows:
            if is_default:
                selected_content = content
                break

        if not selected_content:
            selected_content = type_rows[0][1]

        if selected_content:
            values[legacy_key] = selected_content

    return merge_core_template_values(values)


async def get_core_template_by_id(db: AsyncSession, template_id: int) -> CoreTemplate | None:
    return (await db.execute(select(CoreTemplate).where(CoreTemplate.id == template_id))).unique().scalar_one_or_none()


async def get_core_templates(
    db: AsyncSession,
    template_type: CoreTemplateType | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> tuple[list[CoreTemplate], int]:
    query = select(CoreTemplate)
    if template_type is not None:
        query = query.where(CoreTemplate.template_type == template_type.value)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0

    query = query.order_by(CoreTemplate.template_type.asc(), CoreTemplate.id.asc())
    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)

    rows = (await db.execute(query)).scalars().all()
    return rows, total


async def get_core_templates_simple(
    db: AsyncSession,
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    template_type: CoreTemplateType | None = None,
    sort: list[CoreTemplateSortingOptionsSimple] | None = None,
    skip_pagination: bool = False,
) -> tuple[list[tuple[int, str, str, bool]], int]:
    stmt = select(CoreTemplate.id, CoreTemplate.name, CoreTemplate.template_type, CoreTemplate.is_default)

    if search:
        stmt = stmt.where(CoreTemplate.name.ilike(f"%{search.strip()}%"))

    if template_type is not None:
        stmt = stmt.where(CoreTemplate.template_type == template_type.value)

    if sort:
        sort_list = []
        for s in sort:
            if isinstance(s.value, tuple):
                sort_list.extend(s.value)
            else:
                sort_list.append(s.value)
        stmt = stmt.order_by(*sort_list)
    else:
        stmt = stmt.order_by(CoreTemplate.template_type.asc(), CoreTemplate.id.asc())

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0

    if not skip_pagination:
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
    else:
        stmt = stmt.limit(10000)

    rows = (await db.execute(stmt)).all()
    return rows, total


async def count_core_templates_by_type(db: AsyncSession, template_type: CoreTemplateType) -> int:
    count_stmt = select(func.count()).select_from(CoreTemplate).where(CoreTemplate.template_type == template_type.value)
    return (await db.execute(count_stmt)).scalar() or 0


async def get_first_template_by_type(
    db: AsyncSession,
    template_type: CoreTemplateType,
    exclude_id: int | None = None,
) -> CoreTemplate | None:
    stmt = (
        select(CoreTemplate)
        .where(CoreTemplate.template_type == template_type.value)
        .order_by(CoreTemplate.id.asc())
    )
    if exclude_id is not None:
        stmt = stmt.where(CoreTemplate.id != exclude_id)
    return (await db.execute(stmt)).scalars().first()


async def set_default_template(db: AsyncSession, db_template: CoreTemplate) -> CoreTemplate:
    await db.execute(
        update(CoreTemplate)
        .where(CoreTemplate.template_type == db_template.template_type)
        .values(is_default=False)
    )
    db_template.is_default = True
    await db.commit()
    await db.refresh(db_template)
    return db_template


async def create_core_template(db: AsyncSession, core_template: CoreTemplateCreate) -> CoreTemplate:
    type_count = await count_core_templates_by_type(db, core_template.template_type)
    is_first_for_type = type_count == 0
    should_be_default = core_template.is_default or is_first_for_type

    if should_be_default:
        await db.execute(
            update(CoreTemplate)
            .where(CoreTemplate.template_type == core_template.template_type.value)
            .values(is_default=False)
        )

    db_template = CoreTemplate(
        name=core_template.name,
        template_type=core_template.template_type.value,
        content=core_template.content,
        is_default=should_be_default,
        is_system=is_first_for_type,
    )
    db.add(db_template)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(db_template)
    return db_template


async def modify_core_template(
    db: AsyncSession,
    db_template: CoreTemplate,
    modified_template: CoreTemplateModify,
) -> CoreTemplate:
    template_data = modified_template.model_dump(exclude_none=True)

    if modified_template.is_default is True:
        await db.execute(
            update(CoreTemplate)
            .where(CoreTemplate.template_type == db_template.template_type)
            .values(is_default=False)
        )
        db_template.is_default = True

    if "name" in template_data:
        db_template.name = template_data["name"]
    if "content" in template_data:
        db_template.content = template_data["content"]

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(db_template)
    return db_template


async def remove_core_template(db: AsyncSession, db_template: CoreTemplate) -> None:
    await db.delete(db_template)
    await db.commit()
