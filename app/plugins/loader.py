"""Discover and import plugins from ``PLUGINS_DIR``.

Each enabled id must be a folder ``<PLUGINS_DIR>/<id>/`` with a ``plugin.json`` manifest. The folder is
imported as package ``pasarguard_plugins.<id>`` without adding it to ``sys.path``. A plugin that fails
to load is recorded as failed and skipped; the panel always starts.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import inspect
import json
import re
import sys
import types
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from app.plugins.context import PluginContext
from app.plugins.registry import PluginRecord
from app.utils.logger import get_logger
from app.version import __version__

logger = get_logger("plugins")

PACKAGE_ROOT = "pasarguard_plugins"
PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MANIFEST = "plugin.json"


class PluginLoadError(Exception):
    pass


def read_manifest(folder: Path, plugin_id: str) -> dict[str, Any]:
    manifest_path = folder / MANIFEST
    if not manifest_path.is_file():
        raise PluginLoadError(f"{MANIFEST} not found in {folder}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PluginLoadError(f"invalid {MANIFEST}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PluginLoadError(f"{MANIFEST} must be a JSON object")
    if manifest.get("id") != plugin_id:
        raise PluginLoadError(f"{MANIFEST} id {manifest.get('id')!r} does not match folder name {plugin_id!r}")
    settings_schema = manifest.get("settings_schema")
    if settings_schema is not None and not (
        isinstance(settings_schema, dict) and settings_schema.get("type") in (None, "object")
    ):
        raise PluginLoadError("settings_schema must be a JSON Schema object with type 'object'")
    ui = manifest.get("ui")
    if ui is not None and not isinstance(ui, str):
        raise PluginLoadError("ui must be a path string")
    entry = manifest.get("entry", "plugin:setup")
    if not isinstance(entry, str) or not re.fullmatch(r"[A-Za-z_][\w.]*:[A-Za-z_]\w*", entry):
        raise PluginLoadError(f"invalid entry {entry!r}, expected 'module:function'")
    return manifest


def check_panel_version(constraint: Any, panel_version: str = __version__) -> None:
    if constraint in (None, ""):
        return
    if not isinstance(constraint, str):
        raise PluginLoadError("panel must be a version constraint string like '>=5.5.0'")
    try:
        allowed = SpecifierSet(constraint)
        current = Version(panel_version)
    except (InvalidSpecifier, InvalidVersion) as exc:
        raise PluginLoadError(f"invalid panel constraint {constraint!r}: {exc}") from exc
    if not allowed.contains(current, prereleases=True):
        raise PluginLoadError(f"requires panel {constraint}, this panel is {panel_version}")


def _ensure_root_package() -> None:
    if PACKAGE_ROOT in sys.modules:
        return
    root = types.ModuleType(PACKAGE_ROOT)
    root.__path__ = []  # children are registered explicitly, never searched on sys.path
    root.__package__ = PACKAGE_ROOT
    sys.modules[PACKAGE_ROOT] = root


def _forget_modules(package_name: str) -> None:
    for name in [name for name in sys.modules if name == package_name or name.startswith(f"{package_name}.")]:
        del sys.modules[name]


def import_entry(folder: Path, plugin_id: str, entry: str):
    """Import ``folder`` as ``pasarguard_plugins.<id>`` and return the entry callable."""
    _ensure_root_package()
    package_name = f"{PACKAGE_ROOT}.{plugin_id}"
    _forget_modules(package_name)

    init_file = folder / "__init__.py"
    if init_file.is_file():
        spec = importlib.util.spec_from_file_location(package_name, init_file, submodule_search_locations=[str(folder)])
    else:
        spec = importlib.machinery.ModuleSpec(package_name, None, is_package=True)
        spec.submodule_search_locations = [str(folder)]
    if spec is None:
        raise PluginLoadError(f"cannot import {folder}")

    module_part, func_name = entry.split(":", 1)
    try:
        package = importlib.util.module_from_spec(spec)
        sys.modules[package_name] = package
        if spec.loader is not None:
            spec.loader.exec_module(package)
        module = importlib.import_module(f"{package_name}.{module_part}")
        setup = getattr(module, func_name, None)
    except Exception:
        _forget_modules(package_name)
        raise
    if not callable(setup):
        _forget_modules(package_name)
        raise PluginLoadError(f"entry {entry!r} is not a callable")
    return setup


def load_plugin(plugins_dir: Path, plugin_id: str, *, runs_panel: bool, runs_scheduler: bool):
    """Load one plugin and call its ``setup``.

    Returns ``(record, pending)`` where ``pending`` is the coroutine of an async ``setup`` (to be awaited at
    startup) or None. On failure the record has ``status="failed"`` and ``context=None``.
    """
    record = PluginRecord(id=plugin_id)
    pending = None
    try:
        if not PLUGIN_ID_RE.fullmatch(plugin_id):
            raise PluginLoadError("invalid plugin id (allowed: a-z, 0-9, '-', '_', up to 64 chars)")
        folder = (plugins_dir / plugin_id).resolve()
        if not folder.is_dir():
            raise PluginLoadError(f"folder {plugins_dir / plugin_id} not found")
        record.path = folder

        manifest = read_manifest(folder, plugin_id)
        record.name = str(manifest.get("name") or plugin_id)
        record.version = str(manifest.get("version") or "")
        record.description = str(manifest.get("description") or "")
        record.settings_schema = manifest.get("settings_schema")
        record.ui = manifest.get("ui")
        check_panel_version(manifest.get("panel"))

        setup = import_entry(folder, plugin_id, manifest.get("entry", "plugin:setup"))
        ctx = PluginContext(
            plugin_id,
            record.version,
            record.settings_schema,
            runs_panel=runs_panel,
            runs_scheduler=runs_scheduler,
        )
        result = setup(ctx)
        if inspect.isawaitable(result):
            pending = result
        record.context = ctx
        record.status = "loaded"
    except Exception as exc:
        record.status = "failed"
        record.error = str(exc) or type(exc).__name__
        record.context = None
        if isinstance(exc, PluginLoadError):
            logger.error(f"Plugin {plugin_id!r} skipped: {record.error}")
        else:
            logger.exception(f"Plugin {plugin_id!r} skipped: {record.error}")
    return record, pending
