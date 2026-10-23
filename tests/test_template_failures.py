"""Broken templates fail the subscription and broken variables fall back; both are logged once per window."""

import logging
from types import SimpleNamespace

import pytest

from app.models.client_template import TemplateSource
from app.models.settings import CustomVariable
from app.subscription import ClashConfiguration
from app.subscription.share import (
    TemplateRenderError,
    _render_client_templates,
    apply_custom_format_variables,
    get_effective_custom_variables,
)
from app.templates import failures
from app.templates.failures import report_failure, template_ref


@pytest.fixture(autouse=True)
def _clean(caplog):
    failures._logged.clear()
    with caplog.at_level(logging.ERROR, logger="template-failures"):
        yield
    failures._logged.clear()


def test_a_source_is_logged_once_per_window_with_the_number_left_out(caplog, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(failures.time, "monotonic", lambda: now[0])
    ref = template_ref(3)

    for _ in range(3):
        report_failure(ref, ValueError("boom"))
    report_failure(template_ref(4), ValueError("another source"))
    assert [r.getMessage() for r in caplog.records] == [
        "template:3 failed to render: boom",
        "template:4 failed to render: another source",
    ]

    now[0] += failures.LOG_WINDOW
    report_failure(ref, ValueError("boom again"))

    assert caplog.records[-1].getMessage() == "template:3 failed to render (2 more since the last report): boom again"


@pytest.mark.parametrize(
    ("content", "template_id"),
    [('{"a": "{{ 1 + }}"}', 7), ('{"a": "{{ USERNAME }}}', 8)],  # does not compile, renders to something not JSON
)
def test_a_broken_client_template_is_reported_by_its_id_and_fails_the_subscription(caplog, content, template_id):
    with pytest.raises(TemplateRenderError, match=f"template {template_id} failed"):
        _render_client_templates(
            {
                "XRAY_SUBSCRIPTION_TEMPLATE": TemplateSource('{"name": "{{ USERNAME }}"}', True, 6),
                "SINGBOX_SUBSCRIPTION_TEMPLATE": TemplateSource(content, True, template_id),
            },
            {"USERNAME": "u"},
        )

    [record] = caplog.records
    assert record.getMessage().startswith(f"template:{template_id} failed to render")


def test_a_broken_variable_is_reported_with_its_owner(caplog):
    admin = SimpleNamespace(
        id=4,
        username="alice",
        custom_variables=[CustomVariable(key="MINE", value="{{ 1 }}", use_jinja=True)],
    )
    user = SimpleNamespace(admin=admin)
    broken_global = CustomVariable(key="THEIRS", value="{{ 1 }}", use_jinja=True)
    variables = get_effective_custom_variables(user, [broken_global])
    # Valid when saved, broken when rendered: a name that no longer exists
    variables[0] = {"key": "THEIRS", "value": "{{ NOPE.x() }}", "use_jinja": True}
    variables[1] = {**variables[1], "value": "{{ NOPE.x() }}"}

    result = apply_custom_format_variables({}, variables)

    assert result["THEIRS"] == "{{ NOPE.x() }}"
    assert {r.getMessage().split(" ")[0] for r in caplog.records} == {"variable:THEIRS", "variable:MINE@admin:4"}


def test_a_broken_clash_template_is_reported_and_still_raises(caplog):
    conf = ClashConfiguration(clash_template_content="{{ NOPE.x() }}", template_ref=template_ref(9))

    with pytest.raises(Exception, match="NOPE|undefined"):
        conf.render()

    assert [r.getMessage().split(" ")[0] for r in caplog.records] == ["template:9"]
