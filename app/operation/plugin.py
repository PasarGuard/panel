from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.db import AsyncSession
from app.db.crud.plugin import save_plugin_settings
from app.models.plugin import PluginResponse, PluginsResponse, PluginStatus
from app.nats.message import MessageTopic
from app.nats.router import router
from app.plugins import registry
from app.plugins.context import PluginContext
from app.plugins.settings import apply_values

from . import BaseOperation


class PluginOperation(BaseOperation):
    @staticmethod
    def get_plugins() -> PluginsResponse:
        plugins = []
        for record in registry.records.values():
            loaded = record.status == "loaded" and record.context is not None
            plugins.append(
                PluginResponse(
                    id=record.id,
                    name=record.name or record.id,
                    version=record.version,
                    description=record.description,
                    status=PluginStatus.loaded if loaded else PluginStatus.failed,
                    error=record.error,
                    has_ui=bool(record.ui) and loaded,
                    settings_schema=record.settings_schema,
                )
            )
        return PluginsResponse(plugins=plugins)

    async def get_validated_plugin(self, plugin_id: str) -> PluginContext:
        record = registry.records.get(plugin_id)
        if record is None or record.context is None:
            await self.raise_error(message="Plugin not found", code=404)
        return record.context

    async def get_plugin_settings(self, plugin_id: str) -> dict[str, Any]:
        ctx = await self.get_validated_plugin(plugin_id)
        return ctx.settings.get()

    async def modify_plugin_settings(self, db: AsyncSession, plugin_id: str, data: dict[str, Any]) -> dict[str, Any]:
        ctx = await self.get_validated_plugin(plugin_id)
        values, errors = ctx.settings.resolve(data)
        if errors:
            detail = {}
            for error in errors:
                where, _, message = error.partition(": ")
                detail[where] = message
            raise HTTPException(status_code=422, detail=detail)

        await save_plugin_settings(db, plugin_id, values)
        await apply_values(ctx, values, notify=True)
        # Other workers reload from the database and fire their own on_change hooks
        await router.publish(MessageTopic.PLUGIN, {"action": "settings", "plugin_id": plugin_id})
        return ctx.settings.get()

    async def get_ui_file(self, plugin_id: str, file_path: str) -> Path:
        """Resolve a file of the plugin UI folder; anything outside it is a 404."""
        record = registry.records.get(plugin_id)
        if record is None or record.context is None or not record.ui or record.path is None:
            await self.raise_error(message="Plugin UI not found", code=404)

        try:
            entry = (record.path / record.ui).resolve()
            ui_root = entry.parent
            target = entry if not file_path else (ui_root / file_path).resolve()
            found = target.is_relative_to(record.path) and target.is_relative_to(ui_root) and target.is_file()
        except ValueError, OSError:  # NUL bytes, names the OS rejects
            found = False
        if not found:
            await self.raise_error(message="File not found", code=404)
        return target
