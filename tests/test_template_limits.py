"""The work and memory a Jinja2 template can cause is bounded, and templates that fit still work."""

from __future__ import annotations

import contextlib
import time

import pytest
from fastapi import HTTPException
from jinja2 import TemplateSyntaxError
from jinja2.sandbox import SecurityError

from app.models.client_template import ClientTemplateType
from app.operation import OperatorType
from app.operation.client_template import ClientTemplateOperation
from app.templates import render_template_string, sandbox_env
from app.templates.filters import CUSTOM_FILTERS
from app.templates.limits import LimitedSandboxEnvironment
from config import template_settings

PROXIES = [{"name": f"p{i}", "port": 1000 + i, "group": i % 3} for i in range(2000)]


@pytest.fixture(scope="module")
def env() -> LimitedSandboxEnvironment:
    environment = LimitedSandboxEnvironment(budget=200_000, max_value_size=100_000, max_output_size=300_000)
    environment.add_filters(CUSTOM_FILTERS)
    return environment


def render(env: LimitedSandboxEnvironment, source: str, **context) -> str:
    return env.render_limited(env.from_string(source), context)


def refused(env: LimitedSandboxEnvironment, source: str, message: str = "", **context) -> None:
    started = time.monotonic()
    with pytest.raises(SecurityError, match=message):
        render(env, source, **context)
    assert time.monotonic() - started < 5, "refusing took too long"


@pytest.mark.parametrize(
    ("source", "context", "expected"),
    [
        (
            "{% for p in proxies if p.group == 1 %}{{ loop.index }}/{{ loop.length }};{% else %}-{% endfor %}",
            {"proxies": PROXIES[:7]},
            "1/2;2/2;",
        ),
        ("{{ 60 * 60 * 24 }} {{ 2 ** 10 }} {{ '%s-%s' | format('a', 'b') }} {{ 5 % 3 }}", {}, "86400 1024 a-b 2"),
        (
            "{% macro tag(n) %}[{{ n | upper }}]{% endmacro %}{% for p in proxies %}{{ tag(p.name) }}{% endfor %}",
            {"proxies": PROXIES[:2]},
            "[P0][P1]",
        ),
        (
            "{{ 'p1' in names }} {{ 'p9' in names }} {{ names[:2] | join }} {% if DAYS < 5 %}soon{% endif %}",
            {"names": ["p0", "p1", "p2"], "DAYS": 3},
            "True False p0p1 soon",
        ),
        ("{{ data | yaml }}", {"data": {"a": [1, 2]}}, "a:\n- 1\n- 2\n"),
    ],
)
def test_templates_that_fit_keep_working(env, source, context, expected):
    assert render(env, source, **context).strip() == expected.strip()


def test_default_limits_leave_room_for_large_subscriptions():
    proxies = [{"name": f"p{i}", "port": 443, "uuid": "u" * 36} for i in range(5000)]
    source = "{% for p in proxies %}{{ 'name: ' ~ p.name ~ ', port: ' ~ p.port | string }}\n{% endfor %}{{ proxies | map(attribute='name') | join(',') | length }}"
    assert render_template_string(source, {"proxies": proxies}).endswith("28889")


@pytest.mark.parametrize(
    "source",
    [
        "{% for i in range(100000) %}{% for j in range(100000) %}{% endfor %}{% endfor %}",
        "{% for a in [1,2,3,4,5,6,7,8,9,10] %}" * 10 + "x" + "{% endfor %}" * 10,
        "{% for i in range(100000) %}{{ range(100000) | join | length }}{% endfor %}",
        "{% for i in range(3000) %}{{ proxies | sort(attribute='port') | map(attribute='name') | join | length }}{% endfor %}",
        "{% for i in range(100000) %}{{ proxies.count(0) }}{% endfor %}",
        # What is built is charged for by its size, not only what a filter is given.
        "{% for i in range(5000) %}{% set x = 'x' * 90000 %}{% endfor %}",
        "{% for i in range(5000) %}{% set x = 'x' | center(90000) %}{% endfor %}",
        "{% for i in range(5000) %}{% set x = proxies + proxies %}{% endfor %}",
        "{% for i in range(5000) %}{% set x = proxies[:] %}{% endfor %}",
        "{% for i in range(5000) %}{% set x = 'x' ~ 'y' * 90000 %}{% endfor %}",
        # `in` and `==` walk what they compare.
        "{% for i in range(5000) %}{% if 'zz' in proxies %}{% endif %}{% endfor %}",
        "{% for i in range(5000) %}{% if proxies == proxies %}{% endif %}{% endfor %}",
        # `is in` is the same walk through a different hook (a Jinja test, not the `in` operator).
        "{% for i in range(5000) %}{% if 'zz' is in proxies %}{% endif %}{% endfor %}",
        # Macros multiply work without any loop, but each call is charged.
        "{% macro f(n) %}{% if n > 0 %}{{ f(n - 1) }}{{ f(n - 1) }}{% endif %}{% endmacro %}{{ f(40) }}",
    ],
)
def test_work_is_bounded(env, source):
    refused(env, source, "too heavy", proxies=PROXIES)


def test_hooks_cannot_be_shadowed_by_the_template(env):
    refused(
        env,
        "{% set limit_iterable = 1 %}{% set guard = 1 %}{% set charge = 1 %}"
        + "{% for a in range(300) %}" * 3
        + "{% endfor %}" * 3,
        "too heavy",
    )


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("{% set a = 'x' * 1000 %}" + "{% set a = a ~ a %}" * 40, "too heavy|too large"),
        ("{% set a = 'x' * 1000 %}" + "{% set a = a | replace('x', 'xx') %}" * 40, "too heavy|too large"),
        ("{{ ('x' * 1000000000) | length }}", "repetition"),
        ("{{ 'x' | center(1500000000) | length }}", "number"),
        ("{{ 'x'.ljust(1000000000) | length }}", "number"),
        ("{{ (10 ** 99999999) | string | length }}", "exponent"),
        ("{{ ('%1000000000s' % 'a') | length }}", "format string"),
        ("{{ '%1000000000s' | format('a') | length }}", "format string"),
        ("{{ '{:>1000000000}'.format(1) | length }}", "format string"),
        ("{% for i in range(10 ** 7) %}{% endfor %}", "number"),
        # Each squaring stays under the per-step exponent cap, but the result still grows exponentially.
        ("{% set ns = namespace(x=2) %}{% for i in range(20) %}{% set ns.x = ns.x * ns.x %}{% endfor %}", "number"),
        # Each exponent is within the cap on its own; chaining them is still unbounded.
        ("{% set a = 2 ** 1000 %}{% set b = a ** 1000 %}{{ b ** 1000 }}", "number"),
    ],
)
def test_memory_is_bounded(env, source, message):
    refused(env, source, message)


@pytest.mark.parametrize(
    "source",
    [
        "{{ ('%.1000000000f' % 1.0) | length }}",
        "{{ '{:.1000000000f}'.format(1.0) | length }}",
        "{{ '{0:>1000000000}'.format_map({}) | length }}",
    ],
)
def test_format_widths_are_checked_where_they_size_the_result(env, source):
    refused(env, source, "format string")


def test_format_strings_may_contain_large_numbers_elsewhere(env):
    assert render(env, "{{ 'since 1700000000: %s' % 'a' }}") == "since 1700000000: a"
    assert render(env, "{{ 'id 1234567890123 {}'.format('x') }}") == "id 1234567890123 x"
    assert render(env, "{{ 'stamp 1700000000 %s' | format('x') }}") == "stamp 1700000000 x"
    assert render(env, "{{ '{:>10}|{:.3f}|%d%%' .format(1, 2.0) }}") == "         1|2.000|%d%%"
    assert render(env, "{{ '100%% of %d' % 1700000000 }}") == "100% of 1700000000"


def test_output_is_bounded(env):
    refused(env, "{% for i in range(4000) %}{{ 'x' * 100 }}{% endfor %}", "output is too large")


@pytest.mark.parametrize(
    ("source", "construct"),
    [
        ("a\n{% include 'x' %}", "include"),
        ("a\n{% import 'x' as y %}", "import"),
        ("a\n{% from 'x' import y %}", "import"),
        ("a\n{% extends 'x' %}", "extends"),
        ("a\n{% block b %}{% endblock %}", "block"),
        ("a\n{% macro m() %}{{ caller() }}{% endmacro %}{% call m() %}x{% endcall %}", "call blocks"),
        ("a\n{% for x in t recursive %}{{ loop(x) }}{% endfor %}", "recursive loops"),
    ],
)
def test_constructs_that_multiply_work_are_refused_with_their_line(env, source, construct):
    with pytest.raises(TemplateSyntaxError, match=construct) as raised:
        env.from_string(source)
    assert raised.value.lineno == 2


def test_budget_is_per_render_and_required(env):
    assert render(env, "{{ lipsum is defined }}") == "False"
    template = env.from_string("{% for i in range(10000) %}{% endfor %}ok")
    assert [env.render_limited(template, {}) for _ in range(5)] == ["ok"] * 5
    with pytest.raises(LookupError):
        "".join(env.from_string("{% for i in [1] %}x{% endfor %}").generate({}))


def test_the_limits_apply_to_every_render_of_an_admins_template():
    bomb = "{% for i in range(100000) %}{% for j in range(100000) %}{% endfor %}{% endfor %}"
    with pytest.raises(SecurityError, match="too heavy"):
        render_template_string(bomb)
    assert sandbox_env.budget == template_settings.render_budget


async def test_saving_a_template_that_is_too_heavy_is_refused():
    bomb = "{% for i in range(100000) %}{% for j in range(100000) %}{% endfor %}{% endfor %}"
    operator = ClientTemplateOperation(OperatorType.API)

    with pytest.raises(HTTPException, match="too heavy") as refused:
        await operator._validate_template_content(ClientTemplateType.clash_subscription, bomb, use_jinja=True)
    assert refused.value.status_code == 400


def test_output_of_set_blocks_and_macros_is_bounded(env):
    refused(
        env,
        "{% set big = 'x' * 90000 %}{% set s %}{% for i in range(10) %}{{ big }}{% endfor %}{% endset %}ok",
        "output is too large",
    )
    refused(
        env,
        "{% set big = 'x' * 90000 %}{% macro m() %}{{ big }}{% endmacro %}"
        "{% set s %}{% for i in range(10) %}{{ m() }}{% endfor %}{% endset %}ok",
        "output is too large",
    )
    assert render(env, "{% set s %}{% for i in range(10) %}{{ 'ab' }}{% endfor %}{% endset %}{{ s }}") == "ab" * 10


def test_striptags_is_not_available(env):
    with pytest.raises(TemplateSyntaxError, match="striptags"):
        render(env, "{{ '<b>x</b>' | striptags }}")


def test_python_filters_are_charged_by_size(env):
    assert render(env, "{{ 'a b c' | wordwrap(3) | replace('\n', '|') }}") == "a b|c"
    # wordwrap on 98k characters costs about 25k units (measured: ~13 ms)
    small = LimitedSandboxEnvironment(budget=20_000, max_value_size=100_000, max_output_size=300_000)
    refused(small, "{{ ('a ' * 49000) | wordwrap(3) | length }}", "too heavy")
    refused(env, "{{ range(60000) | list | sort | length }}", "too heavy")


@pytest.mark.parametrize(
    "source",
    [
        "{{ ('%.*f' % (2000000000, 1.5)) | length }}",
        "{{ ('%*d' % (2000000000, 1)) | length }}",
        "{{ '{x:{w}}'.format_map({'x': 'a', 'w': 1500000000}) | length }}",
        "{{ '{:{}}'.format('a', 1500000000) | length }}",
        "{{ ('x' * 1000).replace('x', 'y' * 90000) | length }}",
        "{{ ('x' * 1000) | replace('x', 'y' * 90000) | length }}",
        "{{ ('y' * 90000).join(['a'] * 1000) | length }}",
        "{{ (['a'] * 1000) | join('y' * 90000) | length }}",
        "{{ (1).to_bytes(1500000000, 'big') | length }}",
        "{{ 'x\\t'.expandtabs(1500000000) | length }}",
    ],
)
def test_sizes_are_checked_before_anything_is_allocated(env, source):
    refused(env, source)


def test_large_numbers_are_fine_where_they_do_not_size_anything(env):
    assert render(env, "{{ 1700000000 | datetime }}").startswith("20")
    assert render(env, "{{ 5368709120 | bytesformat }}") == "5.0 GB"
    assert render(env, "{{ 3000000 + 1 }} {{ [5368709120, 1] | max }}") == "3000001 5368709120"
    refused(env, "{{ 2 ** 70 }}", "too large")


def test_format_patterns_match_in_linear_time(env):
    started = time.monotonic()
    for hostile in ("{" + ":" * 90000, "%(" * 45000, "{:" * 45000):
        with contextlib.suppress(SecurityError):  # refusing is fine, as long as it is quick
            env.check_format_string(hostile)
    assert time.monotonic() - started < 1


def test_yaml_is_charged_for_being_slow(env):
    conf = {"proxies": [{"name": f"p{i}", "port": i, "opts": {"a": 1, "b": [1, 2]}} for i in range(300)]}
    refused(env, "{% for i in range(100) %}{% set x = conf | yaml %}{% endfor %}", "too heavy", conf=conf)
