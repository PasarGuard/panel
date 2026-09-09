from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Settings
from app.models.settings import SettingsSchema


async def get_settings(db: AsyncSession, *, for_update: bool = False) -> Settings:
    """
    Retrieves the Settings.

    Args:
        db (AsyncSession): Database session.

    Returns:
        Settings: Settings information.
    """
    stmt = select(Settings)
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one_or_none()


async def lock_settings_row(db: AsyncSession) -> Settings:
    """Serialize settings/template mutations, including on SQLite."""
    await db.execute(update(Settings).values(id=Settings.id))
    return await get_settings(db, for_update=True)


async def modify_settings(db: AsyncSession, db_setting: Settings, modify: SettingsSchema) -> Settings:
    settings_data = modify.model_dump(exclude_none=True)

    for key, value in settings_data.items():
        setattr(db_setting, key, value)

    await db.commit()
    await db.refresh(db_setting)
    return db_setting
