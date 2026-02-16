import os
from datetime import datetime as dt, timezone as tz
from typing import Union

import jinja2

from config import (
    CLASH_SUBSCRIPTION_TEMPLATE,
    CUSTOM_TEMPLATES_DIRECTORY,
    SINGBOX_SUBSCRIPTION_TEMPLATE,
    XRAY_SUBSCRIPTION_TEMPLATE,
)

from .filters import CUSTOM_FILTERS

template_directories = ["app/templates"]
if CUSTOM_TEMPLATES_DIRECTORY:
    # User's templates have priority over default templates
    template_directories.insert(0, CUSTOM_TEMPLATES_DIRECTORY)

env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_directories))
env.filters.update(CUSTOM_FILTERS)
env.globals["now"] = lambda: dt.now(tz.utc)


def render_template(template: str, context: Union[dict, None] = None) -> str:
    return env.get_template(template).render(context or {})


DEFAULT_TEMPLATES = {
    XRAY_SUBSCRIPTION_TEMPLATE,
    CLASH_SUBSCRIPTION_TEMPLATE,
    SINGBOX_SUBSCRIPTION_TEMPLATE,
}


def get_subscription_templates() -> dict[str, list[str]]:
    """List available custom subscription template files grouped by format.

    Only scans CUSTOM_TEMPLATES_DIRECTORY (if configured).
    Default templates are excluded since they are already the global fallback.
    """
    if not CUSTOM_TEMPLATES_DIRECTORY:
        return {"xray": [], "clash": [], "singbox": []}

    formats = {"xray": ".json", "clash": ".yml", "singbox": ".json"}
    result: dict[str, list[str]] = {}
    for fmt, ext in formats.items():
        templates: list[str] = []
        fmt_dir = os.path.join(CUSTOM_TEMPLATES_DIRECTORY, fmt)
        if os.path.isdir(fmt_dir):
            for root, _, files in os.walk(fmt_dir):
                for f in sorted(files):
                    if f.endswith(ext):
                        rel = os.path.relpath(os.path.join(root, f), CUSTOM_TEMPLATES_DIRECTORY)
                        if rel not in DEFAULT_TEMPLATES:
                            templates.append(rel)
        result[fmt] = sorted(templates)
    return result
