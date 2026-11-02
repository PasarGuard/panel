from pydantic import BaseModel
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


def merge_settings_section(stored: dict | None, modify: BaseModel) -> dict:
    """
    Merges the fields sent in `modify` into a stored settings section.

    Fields the request left out keep their stored value. Nested settings models merge the same way;
    every other value (lists, dicts, scalars) is replaced as a whole.
    """
    merged = dict(stored or {})
    for name in modify.model_fields_set:
        value = getattr(modify, name)
        if isinstance(value, BaseModel) and isinstance(merged.get(name), dict):
            merged[name] = merge_settings_section(merged[name], value)
        else:
            merged[name] = modify.model_dump(mode="json", include={name})[name]
    return merged


# Sections saved by merging the sent fields into the stored ones. The dashboard sends only part of
# `general`; the other forms send their whole section and clear a value by leaving it out, so those
# sections are still replaced as a whole.
MERGED_SECTIONS = frozenset({"general"})


async def modify_settings(db: AsyncSession, db_setting: Settings, modify: SettingsSchema) -> Settings:
    for key in modify.model_fields_set:
        section = getattr(modify, key)
        if section is None:
            continue
        if key in MERGED_SECTIONS:
            value = merge_settings_section(getattr(db_setting, key), section)
            # The merged section must still be valid on its own (raises pydantic ValidationError).
            type(section).model_validate(value)
        else:
            value = section.model_dump(exclude_none=True)
        # JSON columns are not mutation tracked: assign a new dict.
        setattr(db_setting, key, value)

    await db.commit()
    await db.refresh(db_setting)
    return db_setting
