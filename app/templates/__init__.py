from collections.abc import Mapping
from datetime import UTC, datetime as dt
from functools import lru_cache

from jinja2 import Environment, FileSystemLoader

from app.utils.logger import get_logger
from config import template_settings

from .filters import CUSTOM_FILTERS
from .limits import LimitedSandboxEnvironment

logger = get_logger("templates")

template_directories = ["app/templates"]
if template_settings.custom_templates_directory:
    # User's templates have priority over default templates
    template_directories.insert(0, template_settings.custom_templates_directory)

# Everything rendered here is served as an HTML page, custom templates included.
env = Environment(loader=FileSystemLoader(template_directories), autoescape=True)
env.filters.update(CUSTOM_FILTERS)
env.globals["now"] = lambda: dt.now(UTC)

# Renders what admins write, so it is limited in the work it may cause.
sandbox_env = LimitedSandboxEnvironment(
    budget=template_settings.render_budget,
    max_value_size=template_settings.max_value_size,
    max_output_size=template_settings.max_output_size,
)
sandbox_env.add_filters(CUSTOM_FILTERS)
sandbox_env.globals["now"] = lambda: dt.now(UTC)


def render_template(template: str, context: dict | None = None) -> str:
    return env.get_template(template).render(context or {})


@lru_cache(maxsize=256)
def _compile(template_content: str):
    # from_string() never caches, and compiling costs ~50x more than rendering.
    return sandbox_env.from_string(template_content)


def compile_template(template_content: str, *, cache: bool = True):
    """Compiles admin-written Jinja2. Drafts should pass cache=False, so they do not evict the cached templates."""
    return _compile(template_content) if cache else sandbox_env.from_string(template_content)


def render_compiled(template, context: dict | None = None) -> str:
    try:
        return sandbox_env.render_limited(template, context or {})
    except (MemoryError, RecursionError) as exc:
        # limits.py's budget is meant to make these unreachable; one getting through is worth a trace, unlike
        # an admin's typo, which is routine.
        logger.error("%s rendering a Jinja template, despite the sandbox's budget: %s", type(exc).__name__, exc)
        raise


def render_template_string(template_content: str, context: dict | None = None, *, cache: bool = True) -> str:
    """Renders admin-written Jinja2 within the limits of `sandbox_env`."""
    return render_compiled(compile_template(template_content, cache=cache), context)


def render_variables(text: str, variables: Mapping, *, use_jinja: bool) -> str:
    """Fill `text` with `variables`: Jinja2 when `use_jinja` is True, else str.format_map.

    `use_jinja` is an explicit, author-chosen flag now, not sniffed from the text, so there is no ambiguity with
    format_map's own "{{" escape for a literal brace.
    Failures raise ValueError, which is what callers of format_map already fall back on.
    """
    if not use_jinja:
        return text.format_map(variables)
    try:
        # Block tags leave newlines behind, which are not allowed in header values.
        return render_template_string(text, dict(variables)).strip()
    except Exception as exc:
        raise ValueError(f"Invalid template: {exc}") from exc
