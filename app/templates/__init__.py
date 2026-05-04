from datetime import datetime as dt, timezone as tz
from typing import Union

import jinja2

from config import template_settings

from .filters import CUSTOM_FILTERS

template_directories = ["app/templates"]
if template_settings.custom_templates_directory:
    # User's templates have priority over default templates
    template_directories.insert(0, template_settings.custom_templates_directory)

env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_directories))
env.filters.update(CUSTOM_FILTERS)
env.globals["now"] = lambda: dt.now(tz.utc)


def render_template(template: str, context: Union[dict, None] = None) -> str:
    return env.get_template(template).render(context or {})


def render_template_string(template_content: str, context: Union[dict, None] = None) -> str:
    return env.from_string(template_content).render(context or {})
