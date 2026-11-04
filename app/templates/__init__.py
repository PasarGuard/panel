from datetime import UTC, datetime as dt
from functools import lru_cache

from jinja2 import Environment, FileSystemLoader
from jinja2.sandbox import SandboxedEnvironment

from config import template_settings

from .filters import CUSTOM_FILTERS

template_directories = ["app/templates"]
if template_settings.custom_templates_directory:
    # User's templates have priority over default templates
    template_directories.insert(0, template_settings.custom_templates_directory)

# Everything rendered here is served as an HTML page, custom templates included.
env = Environment(loader=FileSystemLoader(template_directories), autoescape=True)
env.filters.update(CUSTOM_FILTERS)
env.globals["now"] = lambda: dt.now(UTC)

sandbox_env = SandboxedEnvironment()
sandbox_env.filters.update(CUSTOM_FILTERS)
sandbox_env.globals["now"] = lambda: dt.now(UTC)


def render_template(template: str, context: dict | None = None) -> str:
    return env.get_template(template).render(context or {})


@lru_cache(maxsize=64)
def _compile_sandboxed(template_content: str):
    # from_string() never caches, and a large client template takes far longer to compile than to render.
    return sandbox_env.from_string(template_content)


def render_template_string(template_content: str, context: dict | None = None) -> str:
    return _compile_sandboxed(template_content).render(context or {})
