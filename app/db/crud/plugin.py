from datetime import UTC, datetime as dt

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PluginSettings


async def get_plugin_settings(db: AsyncSession, plugin_ids: list[str]) -> dict[str, dict]:
    if not plugin_ids:
        return {}
    rows = (await db.execute(select(PluginSettings).where(PluginSettings.plugin_id.in_(plugin_ids)))).scalars().all()
    return {row.plugin_id: row.data for row in rows}


async def save_plugin_settings(db: AsyncSession, plugin_id: str, data: dict) -> PluginSettings:
    db_settings = await db.get(PluginSettings, plugin_id)
    if db_settings is None:
        db_settings = PluginSettings(plugin_id=plugin_id, data=data)
        db.add(db_settings)
        try:
            await db.commit()
            return db_settings
        except IntegrityError:
            # Another worker inserted the first row at the same moment: update that row instead
            await db.rollback()
            db_settings = await db.get(PluginSettings, plugin_id)
    db_settings.data = data
    db_settings.updated_at = dt.now(UTC)
    await db.commit()
    return db_settings
