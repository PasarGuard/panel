from collections import defaultdict
from enum import Enum

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClientTemplate
from app.models.client_template import ClientTemplateCreate, ClientTemplateModify, ClientTemplateType

TEMPLATE_TYPE_TO_LEGACY_KEY: dict[ClientTemplateType, str] = {
    ClientTemplateType.clash_subscription: "CLASH_SUBSCRIPTION_TEMPLATE",
    ClientTemplateType.xray_subscription: "XRAY_SUBSCRIPTION_TEMPLATE",
    ClientTemplateType.singbox_subscription: "SINGBOX_SUBSCRIPTION_TEMPLATE",
    ClientTemplateType.user_agent: "USER_AGENT_TEMPLATE",
    ClientTemplateType.grpc_user_agent: "GRPC_USER_AGENT_TEMPLATE",
}

ClientTemplateSortingOptionsSimple = Enum(
    "ClientTemplateSortingOptionsSimple",
    {
        "id": ClientTemplate.id.asc(),
        "-id": ClientTemplate.id.desc(),
        "name": ClientTemplate.name.asc(),
        "-name": ClientTemplate.name.desc(),
        "type": ClientTemplate.template_type.asc(),
        "-type": ClientTemplate.template_type.desc(),
    },
)


async def get_client_template_values(db: AsyncSession) -> dict[str, str]:
    try:
        rows = (
            await db.execute(
                select(
                    ClientTemplate.id,
                    ClientTemplate.template_type,
                    ClientTemplate.content,
                    ClientTemplate.is_default,
                ).order_by(ClientTemplate.template_type.asc(), ClientTemplate.id.asc())
            )
        ).all()
    except SQLAlchemyError:
        return {}

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

    return values


async def get_client_template_contents_by_type(db: AsyncSession, template_type: ClientTemplateType) -> dict[int, str]:
    rows = (
        await db.execute(
            select(ClientTemplate.id, ClientTemplate.content).where(ClientTemplate.template_type == template_type.value)
        )
    ).all()
    return {row.id: row.content for row in rows}


async def get_client_template_by_id(db: AsyncSession, template_id: int) -> ClientTemplate | None:
    return (
        (await db.execute(select(ClientTemplate).where(ClientTemplate.id == template_id))).unique().scalar_one_or_none()
    )


async def get_client_templates(
    db: AsyncSession,
    template_type: ClientTemplateType | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> tuple[list[ClientTemplate], int]:
    query = select(ClientTemplate)
    if template_type is not None:
        query = query.where(ClientTemplate.template_type == template_type.value)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0

    query = query.order_by(ClientTemplate.template_type.asc(), ClientTemplate.id.asc())
    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)

    rows = (await db.execute(query)).scalars().all()
    return rows, total


async def get_client_templates_simple(
    db: AsyncSession,
    offset: int | None = None,
    limit: int | None = None,
    search: str | None = None,
    template_type: ClientTemplateType | None = None,
    sort: list[ClientTemplateSortingOptionsSimple] | None = None,
    skip_pagination: bool = False,
) -> tuple[list[tuple[int, str, str, bool]], int]:
    stmt = select(ClientTemplate.id, ClientTemplate.name, ClientTemplate.template_type, ClientTemplate.is_default)

    if search:
        stmt = stmt.where(ClientTemplate.name.ilike(f"%{search.strip()}%"))

    if template_type is not None:
        stmt = stmt.where(ClientTemplate.template_type == template_type.value)

    if sort:
        sort_list = []
        for s in sort:
            if isinstance(s.value, tuple):
                sort_list.extend(s.value)
            else:
                sort_list.append(s.value)
        stmt = stmt.order_by(*sort_list)
    else:
        stmt = stmt.order_by(ClientTemplate.template_type.asc(), ClientTemplate.id.asc())

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


async def count_client_templates_by_type(db: AsyncSession, template_type: ClientTemplateType) -> int:
    count_stmt = (
        select(func.count()).select_from(ClientTemplate).where(ClientTemplate.template_type == template_type.value)
    )
    return (await db.execute(count_stmt)).scalar() or 0


async def get_first_template_by_type(
    db: AsyncSession,
    template_type: ClientTemplateType,
    exclude_id: int | None = None,
    exclude_ids: list[int] | set[int] | None = None,
) -> ClientTemplate | None:
    stmt = (
        select(ClientTemplate)
        .where(ClientTemplate.template_type == template_type.value)
        .order_by(ClientTemplate.id.asc())
    )
    if exclude_id is not None:
        stmt = stmt.where(ClientTemplate.id != exclude_id)
    if exclude_ids:
        stmt = stmt.where(ClientTemplate.id.not_in(list(exclude_ids)))
    return (await db.execute(stmt)).scalars().first()


async def set_default_template(db: AsyncSession, db_template: ClientTemplate) -> ClientTemplate:
    await db.execute(
        update(ClientTemplate).where(ClientTemplate.template_type == db_template.template_type).values(is_default=False)
    )
    db_template.is_default = True
    await db.commit()
    await db.refresh(db_template)
    return db_template


async def create_client_template(db: AsyncSession, client_template: ClientTemplateCreate) -> ClientTemplate:
    type_count = await count_client_templates_by_type(db, client_template.template_type)
    is_first_for_type = type_count == 0
    should_be_default = client_template.is_default or is_first_for_type

    if should_be_default:
        await db.execute(
            update(ClientTemplate)
            .where(ClientTemplate.template_type == client_template.template_type.value)
            .values(is_default=False)
        )

    db_template = ClientTemplate(
        name=client_template.name,
        template_type=client_template.template_type.value,
        content=client_template.content,
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


async def modify_client_template(
    db: AsyncSession,
    db_template: ClientTemplate,
    modified_template: ClientTemplateModify,
) -> ClientTemplate:
    template_data = modified_template.model_dump(exclude_none=True)

    if modified_template.is_default is True:
        await db.execute(
            update(ClientTemplate)
            .where(ClientTemplate.template_type == db_template.template_type)
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


async def remove_client_template(db: AsyncSession, db_template: ClientTemplate) -> None:
    await db.delete(db_template)
    await db.commit()


async def remove_client_templates(db: AsyncSession, template_ids: list[int]) -> None:
    """
    Removes multiple client templates from the database by ID.

    Args:
        db (AsyncSession): Database session.
        template_ids (list[int]): List of template IDs to remove.
    """
    if not template_ids:
        return

    await db.execute(delete(ClientTemplate).where(ClientTemplate.id.in_(template_ids)))
    await db.commit()
