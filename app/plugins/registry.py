"""Process-wide state of the plugin system. Empty when ``PLUGINS`` is unset."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.plugins.context import PluginContext


@dataclass
class PluginRecord:
    id: str
    name: str = ""
    version: str = ""
    description: str = ""
    path: Path | None = None
    status: str = "failed"  # "loaded" | "failed"
    error: str | None = None
    settings_schema: dict[str, Any] | None = None
    ui: str | None = None
    context: PluginContext | None = field(default=None, repr=False)


# Every plugin listed in PLUGINS, in load order, loaded or failed.
records: dict[str, PluginRecord] = {}
# Contexts of plugins whose setup() finished; hooks read only these. Empty list = plugin system off.
active: list[PluginContext] = []


def get_active(plugin_id: str) -> PluginContext | None:
    for ctx in active:
        if ctx.id == plugin_id:
            return ctx
    return None


def reset() -> None:
    """Forget all plugins (tests)."""
    records.clear()
    active.clear()
