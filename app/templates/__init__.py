from datetime import datetime as dt, timezone as tz
from typing import Union

from jinja2 import Environment, FileSystemLoader
from jinja2.sandbox import SandboxedEnvironment

from config import template_settings

from .filters import CUSTOM_FILTERS

template_directories = ["app/templates"]
if template_settings.custom_templates_directory:
    # User's templates have priority over default templates
    template_directories.insert(0, template_settings.custom_templates_directory)

env = Environment(loader=FileSystemLoader(template_directories))
env.filters.update(CUSTOM_FILTERS)
env.globals["now"] = lambda: dt.now(tz.utc)

sandbox_env = SandboxedEnvironment()
sandbox_env.filters.update(CUSTOM_FILTERS)
sandbox_env.globals["now"] = lambda: dt.now(tz.utc)


def render_template(template: str, context: Union[dict, None] = None) -> str:
    return env.get_template(template).render(context or {})


def render_template_string(template_content: str, context: Union[dict, None] = None) -> str:
    return sandbox_env.from_string(template_content).render(context or {})
