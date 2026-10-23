"""Helpers for plugin tests: tiny fixture plugins in a temp dir and a clean registry."""

import json
import sys
import textwrap
from pathlib import Path

from app.plugins import manager, registry


def make_plugin(
    plugins_dir: Path,
    plugin_id: str,
    code: str,
    *,
    manifest: dict | None = None,
    files: dict[str, str] | None = None,
) -> Path:
    folder = plugins_dir / plugin_id
    folder.mkdir(parents=True, exist_ok=True)
    data = {"id": plugin_id, "name": plugin_id.title(), "version": "1.0.0", "panel": ">=5.5.0", "entry": "plugin:setup"}
    data.update(manifest or {})
    (folder / "plugin.json").write_text(json.dumps(data), encoding="utf-8")
    (folder / "plugin.py").write_text(textwrap.dedent(code), encoding="utf-8")
    for name, content in (files or {}).items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")
    return folder


def route_paths(routes) -> list[str]:
    """Full paths of all routes, including lazily included routers (FastAPI >= 0.14x)."""
    paths = []
    for route in routes:
        if hasattr(route, "effective_candidates"):
            paths.extend(route_paths(route.effective_candidates()))
        elif getattr(route, "path", None) is not None:
            paths.append(route.path)
    return paths


def forget_plugin_modules() -> None:
    for name in [
        name for name in sys.modules if name == "pasarguard_plugins" or name.startswith("pasarguard_plugins.")
    ]:
        del sys.modules[name]


def reset_plugins() -> None:
    for _, coro in manager._pending:
        coro.close()
    manager._pending.clear()
    registry.reset()
    forget_plugin_modules()
