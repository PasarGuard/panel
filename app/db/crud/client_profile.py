from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClientProfile, User, UserTemplate
from app.models.client_profile import (
    ClientProfileCreate,
    ClientProfileListQuery,
    ClientProfileModify,
    ClientProfileSimpleListQuery,
    ClientProfileSimpleSortField,
    ClientProfileSimpleSortOption,
)


def _build_client_profile_simple_sort_clause(sort_option: ClientProfileSimpleSortOption):
    field_map = {
        ClientProfileSimpleSortField.id: ClientProfile.id,
        ClientProfileSimpleSortField.profile_name: ClientProfile.name,
    }
    column = field_map[sort_option.field]
    return column.desc() if sort_option.value.startswith("-") else column.asc()


def _dump_templates(templates: dict) -> dict[str, int] | None:
    return {str(getattr(key, "value", key)): value for key, value in templates.items()} or None


def _dump_settings(settings) -> dict | None:
    return settings.model_dump(mode="json", exclude_defaults=True) or None


async def get_client_profile_by_id(db: AsyncSession, profile_id: int) -> ClientProfile | None:
    return (await db.execute(select(ClientProfile).where(ClientProfile.id == profile_id))).scalar_one_or_none()


async def get_all_client_profiles(db: AsyncSession) -> list[ClientProfile]:
    return list((await db.execute(select(ClientProfile).order_by(ClientProfile.id.asc()))).scalars().all())


async def count_users_by_client_profile(db: AsyncSession, profile_ids: list[int]) -> dict[int, int]:
    if not profile_ids:
        return {}
    rows = (
        await db.execute(
            select(User.client_profile_id, func.count(User.id))
            .where(User.client_profile_id.in_(profile_ids))
            .group_by(User.client_profile_id)
        )
    ).all()
    return {profile_id: count for profile_id, count in rows}


async def get_client_profiles(
    db: AsyncSession,
    query: ClientProfileListQuery,
) -> tuple[list[ClientProfile], int]:
    stmt = select(ClientProfile)
    if query.ids:
        stmt = stmt.where(ClientProfile.id.in_(query.ids))
    if query.search:
        stmt = stmt.where(ClientProfile.name.ilike(f"%{query.search.strip()}%"))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0

    stmt = stmt.order_by(ClientProfile.id.asc())
    if query.offset:
        stmt = stmt.offset(query.offset)
    if query.limit:
        stmt = stmt.limit(query.limit)

    rows = (await db.execute(stmt)).scalars().all()
    return list(rows), total


async def get_client_profiles_simple(
    db: AsyncSession,
    query: ClientProfileSimpleListQuery,
) -> tuple[list[tuple[int, str]], int]:
    stmt = select(ClientProfile.id, ClientProfile.name)

    if query.ids:
        stmt = stmt.where(ClientProfile.id.in_(query.ids))
    if query.search:
        stmt = stmt.where(ClientProfile.name.ilike(f"%{query.search.strip()}%"))

    if query.sort:
        stmt = stmt.order_by(*[_build_client_profile_simple_sort_clause(sort_option) for sort_option in query.sort])
    else:
        stmt = stmt.order_by(ClientProfile.id.asc())

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0

    if not query.all:
        if query.offset:
            stmt = stmt.offset(query.offset)
        if query.limit:
            stmt = stmt.limit(query.limit)
    else:
        stmt = stmt.limit(10000)

    rows = (await db.execute(stmt)).all()
    return rows, total


async def get_client_profiles_using_templates(db: AsyncSession, template_ids: list[int] | set[int]) -> list[str]:
    """Names of profiles whose templates reference any of the given client template ids."""
    template_id_set = set(template_ids)
    if not template_id_set:
        return []
    rows = (await db.execute(select(ClientProfile.name, ClientProfile.templates))).all()
    return [
        row.name
        for row in rows
        if isinstance(row.templates, dict) and template_id_set.intersection(row.templates.values())
    ]


async def create_client_profile(db: AsyncSession, client_profile: ClientProfileCreate) -> ClientProfile:
    db_profile = ClientProfile(
        name=client_profile.name,
        note=client_profile.note,
        templates=_dump_templates(client_profile.templates),
        settings=_dump_settings(client_profile.settings),
    )
    db.add(db_profile)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(db_profile)
    return db_profile


async def modify_client_profile(
    db: AsyncSession,
    db_profile: ClientProfile,
    modified_profile: ClientProfileModify,
) -> ClientProfile:
    fields_set = modified_profile.model_fields_set

    if modified_profile.name is not None:
        db_profile.name = modified_profile.name
    if "note" in fields_set:
        db_profile.note = modified_profile.note or None
    if "templates" in fields_set:
        db_profile.templates = _dump_templates(modified_profile.templates or {})
    if "settings" in fields_set:
        db_profile.settings = _dump_settings(modified_profile.settings) if modified_profile.settings else None

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    await db.refresh(db_profile)
    return db_profile


async def _detach_client_profiles(db: AsyncSession, profile_ids: list[int]) -> None:
    # ondelete=SET NULL is not enforced on SQLite (no foreign_keys pragma), so detach explicitly.
    await db.execute(update(User).where(User.client_profile_id.in_(profile_ids)).values(client_profile_id=None))
    await db.execute(
        update(UserTemplate).where(UserTemplate.client_profile_id.in_(profile_ids)).values(client_profile_id=None)
    )


async def remove_client_profiles(db: AsyncSession, profile_ids: list[int]) -> None:
    if not profile_ids:
        return
    await _detach_client_profiles(db, profile_ids)
    await db.execute(delete(ClientProfile).where(ClientProfile.id.in_(profile_ids)))
    await db.commit()


async def get_existing_user_ids(db: AsyncSession, user_ids: list[int], admin_id: int | None = None) -> set[int]:
    stmt = select(User.id).where(User.id.in_(user_ids))
    if admin_id is not None:
        stmt = stmt.where(User.admin_id == admin_id)
    return set((await db.execute(stmt)).scalars().all())


async def set_users_client_profile(
    db: AsyncSession,
    profile_id: int | None,
    *,
    user_ids: list[int] | None = None,
    current_profile_id: int | None = None,
    admin_id: int | None = None,
) -> int:
    """One UPDATE for the selection: by ids, and/or every user currently on current_profile_id."""
    stmt = update(User)
    if user_ids is not None:
        stmt = stmt.where(User.id.in_(user_ids))
    if current_profile_id is not None:
        stmt = stmt.where(User.client_profile_id == current_profile_id)
    if admin_id is not None:
        stmt = stmt.where(User.admin_id == admin_id)
    result = await db.execute(stmt.values(client_profile_id=profile_id).execution_options(synchronize_session=False))
    await db.commit()
    return result.rowcount or 0
