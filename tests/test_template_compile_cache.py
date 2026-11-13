from unittest.mock import patch

import pytest
from jinja2.exceptions import SecurityError

from app.templates import _compile_sandboxed, render_template_string, sandbox_env


def test_same_template_is_compiled_once_and_rendered_per_context():
    _compile_sandboxed.cache_clear()
    with patch.object(sandbox_env, "from_string", wraps=sandbox_env.from_string) as from_string:
        assert render_template_string("{{ name }}", {"name": "a"}) == "a"
        assert render_template_string("{{ name }}", {"name": "b"}) == "b"
    assert from_string.call_count == 1


def test_edited_template_is_compiled_again():
    _compile_sandboxed.cache_clear()
    assert render_template_string("first {{ name }}", {"name": "a"}) == "first a"
    assert render_template_string("second {{ name }}", {"name": "a"}) == "second a"


def test_sandbox_still_applies_to_cached_template():
    _compile_sandboxed.cache_clear()
    template = "{{ name.__class__.__mro__ }}"
    for _ in range(2):
        with pytest.raises(SecurityError):
            render_template_string(template, {"name": "a"})


def test_uncached_render_does_not_retain_the_template():
    _compile_sandboxed.cache_clear()
    assert render_template_string("{{ name }}", {"name": "a"}, cache=False) == "a"
    assert _compile_sandboxed.cache_info().currsize == 0
