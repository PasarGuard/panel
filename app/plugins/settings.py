"""Plugin settings: stored in ``plugin_settings``, cached per process, refreshed across workers via NATS."""

from __future__ import annotations

import asyncio
import inspect

from app.db import GetDB
from app.db.crud.plugin import get_plugin_settings
from app.plugins import registry
from app.plugins.context import PluginContext
from app.utils.logger import get_logger

logger = get_logger("plugins")

CHANGE_HOOK_TIMEOUT = 10.0


def _contexts(plugin_ids: list[str] | None = None) -> list[PluginContext]:
    return [
        record.context
        for record in registry.records.values()
        if record.context is not None and (plugin_ids is None or record.id in plugin_ids)
    ]


async def fire_change(ctx: PluginContext) -> None:
    for hook in list(ctx.settings.change_hooks):
        try:
            result = hook(ctx.settings.get())
            if inspect.isawaitable(result):
                await asyncio.wait_for(result, timeout=CHANGE_HOOK_TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception:
            ctx.logger.exception("Plugin settings on_change handler failed")


async def apply_values(ctx: PluginContext, values: dict, *, notify: bool) -> None:
    changed = values != ctx.settings.get()
    ctx.settings.set_values(values)
    if not changed:
        return
    if ctx.subscription.transforms or ctx.subscription.variable_hooks:
        from app.subscription.config_cache import clear_sub_config_cache

        # Cached subscription bodies may embed output of this plugin's transforms/variables
        clear_sub_config_cache()
    if notify:
        await fire_change(ctx)


async def load_settings_from_db(plugin_ids: list[str] | None = None, *, notify: bool) -> None:
    """Read stored settings for loaded plugins (startup, NATS refresh). Invalid data falls back to defaults."""
    contexts = _contexts(plugin_ids)
    if not contexts:
        return
    try:
        async with GetDB() as db:
            stored = await get_plugin_settings(db, [ctx.id for ctx in contexts])
    except Exception as exc:
        logger.warning(f"Could not read plugin settings, keeping current values: {exc}")
        return

    for ctx in contexts:
        values, errors = ctx.settings.resolve(stored.get(ctx.id))
        if errors:
            logger.warning(f"Stored settings of plugin {ctx.id!r} are invalid ({'; '.join(errors)}), using defaults")
            values = ctx.settings.defaults()
        await apply_values(ctx, values, notify=notify)


async def handle_plugin_message(data: dict) -> None:
    """NATS handler: another worker saved plugin settings."""
    if data.get("action") != "settings":
        return
    plugin_id = data.get("plugin_id")
    if isinstance(plugin_id, str):
        await load_settings_from_db([plugin_id], notify=True)
