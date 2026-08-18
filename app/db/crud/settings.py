from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Settings
from app.models.settings import SettingsSchema


async def get_settings(db: AsyncSession) -> Settings:
    """
    Retrieves the Settings.

    Args:
        db (AsyncSession): Database session.

    Returns:
        Settings: Settings information.
    """
    return (await db.execute(select(Settings))).scalar_one_or_none()


async def modify_settings(db: AsyncSession, db_setting: Settings, modify: SettingsSchema) -> Settings:
    """Apply explicitly supplied settings while preserving meaningful nested nulls."""
    # Ignore omitted top-level sections, but preserve explicit ``None`` values
    # inside a section. Some settings use ``None`` as a meaningful value (for
    # example, disabling an automatic retention policy).
    settings_data = {
        key: value
        for key, value in modify.model_dump(include=modify.model_fields_set).items()
        if value is not None
    }

    for key, value in settings_data.items():
        setattr(db_setting, key, value)

    await db.commit()
    await db.refresh(db_setting)
    return db_setting
