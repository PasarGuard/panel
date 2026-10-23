"""Jinja2 in subscription headers, custom variables and client templates."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.templates as templates_module
from app.db.models import UserStatus
from app.models.admin import AdminDetails, AdminRoleData
from app.models.admin_role import CRUDPermissions, RolePermissions
from app.models.client_template import ClientTemplateType, TemplateSource
from app.models.settings import CustomVariable
from app.models.subscription import SubscriptionInboundData, TLSConfig, XHTTPTransportConfig
from app.operation.client_template import InvalidTemplateContent, check_template_content
from app.operation.subscription import SubscriptionOperation
from app.subscription import config_cache
from app.subscription.share import (
    HostPreparer,
    TemplateRenderError,
    _render_client_templates,
    apply_custom_format_variables,
    generate_subscription,
    process_inbounds_and_tags,
    setup_format_variables,
)
from app.subscription.xray import XrayConfiguration
from app.templates import render_variables
from app.templates.variables import REQUEST_VARIABLES, SAMPLE_FORMAT_VARIABLES, UNLIMITED_FORMAT_VARIABLES

URL = "https://sub.example/sub/abc123.signature"


@pytest.fixture(autouse=True)
def _clear_sub_config_cache():
    config_cache.clear_sub_config_cache()
    yield
    config_cache.clear_sub_config_cache()


def test_memory_and_recursion_errors_are_logged_not_hidden(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    # An admin's typo must not look the same in the logs as a real resource-exhaustion signal.
    def boom(*args, **kwargs):
        raise MemoryError("simulated")

    monkeypatch.setattr(templates_module, "_compile", lambda content: SimpleNamespace(render=boom))
    with caplog.at_level("ERROR"), pytest.raises(ValueError, match="Invalid template"):
        render_variables("{{ 1 }}", {}, use_jinja=True)
    assert "MemoryError" in caplog.text


def test_jinja_expression_and_block():
    variables = {"url": URL, "DAYS_LEFT": 3}
    assert render_variables("{{ url.split('/')[-1] }}", variables, use_jinja=True) == "abc123.signature"
    # Block tags leave newlines behind; they are stripped so the result is a valid header value.
    text = "{% if DAYS_LEFT < 5 %}\nexpires soon\n{% endif %}\n"
    assert render_variables(text, variables, use_jinja=True) == "expires soon"
    # use_jinja is an explicit flag, not sniffed: with it off, "{{" is just format_map's escape for a literal brace.
    assert render_variables("{{ DAYS_LEFT }}", variables, use_jinja=False) == "{ DAYS_LEFT }"


def test_custom_variable_can_use_jinja_and_url():
    custom = [
        {"key": "TOKEN", "value": "{{ url.split('/')[-1] }}", "use_jinja": True},
        {"key": "PLAIN", "value": "{USERNAME}!"},
    ]
    variables = defaultdict(lambda: "<missing>", {"USERNAME": "bob"})

    # No `url` yet (setup_format_variables): the raw text stays until it is applied again.
    apply_custom_format_variables(variables, custom)
    assert variables["TOKEN"] == "{{ url.split('/')[-1] }}"
    assert variables["PLAIN"] == "bob!"

    variables["url"] = URL
    apply_custom_format_variables(variables, custom)
    assert variables["TOKEN"] == "abc123.signature"


def test_custom_variable_validation():
    assert CustomVariable(key="A", value="{{ USERNAME | upper }}", use_jinja=True).value == "{{ USERNAME | upper }}"
    with pytest.raises(ValidationError):
        CustomVariable(key="A", value="{% if USERNAME %}", use_jinja=True)
    # Without the flag a double brace is str.format_map's escape for a literal brace, so there is nothing to reject.
    assert CustomVariable(key="A", value="{{amount}}").value == "{{amount}}"

    # "∞" stands in for DAYS_LEFT and friends when a user has no limit or expiry.
    with pytest.raises(ValidationError, match="not supported"):
        CustomVariable(key="A", value="{{ 'soon' if DAYS_LEFT < 5 else '' }}", use_jinja=True)
    CustomVariable(key="A", value="{{ 'soon' if DAYS_LEFT is number and DAYS_LEFT < 5 else '' }}", use_jinja=True)
    # Stored plain values are validated on every load, so these lenient ones must keep loading.
    for value in ("{DAYS_LEFT:s}", "{DAYS_LEFT:.2}", "{USAGE_PERCENTAGE:s}"):
        assert CustomVariable(key="A", value=value).value == value
    with pytest.raises(ValidationError):
        CustomVariable(key="A", value="{DAYS_LEFT")


def test_custom_variable_may_not_render_a_line_break():
    # Headers refuse them, and block tags leave them behind inside the text
    with pytest.raises(ValidationError, match="line break"):
        CustomVariable(key="A", value="{% if USERNAME %}x{% endif %}\n{% if USERNAME %}y{% endif %}", use_jinja=True)
    assert CustomVariable(key="A", value="{% if USERNAME %}x{% endif %}\n", use_jinja=True)
    assert CustomVariable(key="HOSTS", value="x").key == "HOSTS"


def test_header_reaches_jinja_only_through_a_custom_variable():
    # setup_format_variables resolves custom variables (Jinja or not) into plain strings before anything that
    # formats a header, announce or profile_title text ever runs, so {GREETING} below is a normal format_map
    # field by the time it gets there -- the header text itself never touches Jinja.
    user = SimpleNamespace(
        username="bob",
        status=UserStatus.active,
        data_limit=None,
        used_traffic=0,
        expire=None,
        on_hold_expire_duration=None,
        admin=None,
    )
    custom_variables = [CustomVariable(key="GREETING", value="{{ USERNAME | upper }}!", use_jinja=True)]
    format_variables = setup_format_variables(user, custom_variables)
    assert format_variables["GREETING"] == "BOB!"

    sub_settings = SimpleNamespace(announce="Hello {GREETING}", announce_url="https://{GREETING}.example")
    assert SubscriptionOperation._format_announce(sub_settings, format_variables) == "Hello BOB!"
    assert SubscriptionOperation._format_announce_url(sub_settings, format_variables) == "https://BOB!.example"


def sources(templates: dict) -> dict[str, TemplateSource]:
    return {key: TemplateSource(*value, id=number) for number, (key, value) in enumerate(templates.items(), 1)}


def test_client_templates_render_with_user_variables():
    variables = {"USERNAME": "bob"}
    rendered = _render_client_templates(
        sources(
            {
                "XRAY_SUBSCRIPTION_TEMPLATE": ('{"outbounds": [], "tag": "{{ USERNAME }}"}', True),
                "SINGBOX_SUBSCRIPTION_TEMPLATE": ('{"a": {"b": 1}}', False),
                # Needs `conf`, which only exists once the proxies are added.
                "CLASH_SUBSCRIPTION_TEMPLATE": ("{{ conf.proxies }}", True),
            }
        ),
        variables,
    )
    assert json.loads(rendered["XRAY_SUBSCRIPTION_TEMPLATE"])["tag"] == "bob"
    assert rendered["SINGBOX_SUBSCRIPTION_TEMPLATE"] == '{"a": {"b": 1}}'
    assert rendered["CLASH_SUBSCRIPTION_TEMPLATE"] == "{{ conf.proxies }}"
    assert XrayConfiguration(xray_template_content=rendered["XRAY_SUBSCRIPTION_TEMPLATE"]).template["tag"] == "bob"


@pytest.mark.asyncio
async def test_generate_subscription_renders_templates_and_custom_variables(monkeypatch: pytest.MonkeyPatch):
    user = SimpleNamespace(
        id=7,
        username="bob",
        status=UserStatus.active,
        inbounds=[],
        data_limit=None,
        used_traffic=0,
        expire=None,
        on_hold_expire_duration=None,
        admin=None,
        proxy_settings=SimpleNamespace(dict=dict),
    )
    templates = {
        "USER_AGENT_TEMPLATE": ("", False),
        "GRPC_USER_AGENT_TEMPLATE": ("", False),
        "XRAY_SUBSCRIPTION_TEMPLATE": ('{"outbounds": [{"tag": "{{ GREETING }}"}]}', True),
        "CLASH_SUBSCRIPTION_TEMPLATE": (
            "user: {{ USERNAME }}\ngreeting: {{ GREETING }}\nproxies: {{ conf.proxies | length }}",
            True,
        ),
        "SINGBOX_SUBSCRIPTION_TEMPLATE": ("{}", False),
    }
    settings = SimpleNamespace(
        custom_variables=[CustomVariable(key="GREETING", value="{{ USERNAME | upper }}!", use_jinja=True)]
    )
    monkeypatch.setattr(
        "app.subscription.share.subscription_client_templates", AsyncMock(return_value=sources(templates))
    )
    monkeypatch.setattr("app.subscription.share.subscription_settings", AsyncMock(return_value=settings))
    monkeypatch.setattr("app.subscription.share.host_manager.get_all_hosts", AsyncMock(return_value={}))

    clash = await generate_subscription(user, "clash", False)
    assert clash == "user: bob\ngreeting: BOB!\nproxies: 0"


XRAY = ClientTemplateType.xray_subscription


def _xray(extra: str) -> str:
    return '{\n"inbounds": [{}],\n"outbounds": [{}],\n' + extra + "\n}"


def test_template_check_clash_is_always_jinja_even_if_not_asked():
    # Clash always needs `conf`, so the flag passed for it is advisory at most.
    check_template_content(
        ClientTemplateType.clash_subscription, "user: {{ USERNAME }}\nn: {{ conf.proxies | length }}", use_jinja=False
    )
    with pytest.raises(InvalidTemplateContent):
        check_template_content(ClientTemplateType.clash_subscription, "user: {{ NOPE.x() }}", use_jinja=False)


def test_template_check_reports_source_lines():
    with pytest.raises(InvalidTemplateContent) as syntax:
        check_template_content(XRAY, _xray('"a": {% if %}'), use_jinja=True)
    assert syntax.value.line == 4

    with pytest.raises(InvalidTemplateContent) as runtime:
        check_template_content(XRAY, _xray('"a": "{{ NOPE.split(",") }}"'), use_jinja=True)
    assert runtime.value.line == 4

    with pytest.raises(InvalidTemplateContent) as clash:
        check_template_content(ClientTemplateType.clash_subscription, "a: 1\nb: {{ NOPE.x() }}", use_jinja=True)
    assert clash.value.line == 2


def test_template_check_does_not_trust_lines_of_rendered_output():
    with pytest.raises(InvalidTemplateContent) as plain:
        check_template_content(XRAY, _xray('"a": ,'), use_jinja=False)
    assert plain.value.line == 4
    assert "rendered output" not in str(plain.value)

    with pytest.raises(InvalidTemplateContent) as rendered:
        check_template_content(XRAY, _xray('"a": {{ USERNAME }},'), use_jinja=True)
    assert rendered.value.line is None
    assert "rendered output" in str(rendered.value)

    with pytest.raises(InvalidTemplateContent) as structure:
        check_template_content(XRAY, '{"inbounds": [], "outbounds": [{}]}', use_jinja=True)
    assert structure.value.line is None


def test_template_check_uses_user_variables_with_their_runtime_types():
    check_template_content(XRAY, _xray('"a": {{ (DAYS_LEFT is number and DAYS_LEFT < 5) | tojson }}'), use_jinja=True)
    with pytest.raises(InvalidTemplateContent, match="without data limit or expiry"):
        check_template_content(XRAY, _xray('"a": {{ (DAYS_LEFT < 5) | tojson }}'), use_jinja=True)

    # Custom variables are known by name; the request's own variables are not.
    content = _xray('"a": "{{ MY_VAR.split(",")[0] }}"')
    check_template_content(XRAY, content, ["MY_VAR"], use_jinja=True)
    with pytest.raises(InvalidTemplateContent, match="'MY_VAR' is undefined"):
        check_template_content(XRAY, content, use_jinja=True)
    with pytest.raises(InvalidTemplateContent, match="'url' is undefined"):
        check_template_content(XRAY, _xray('"a": "{{ url.split(",")[0] }}"'), use_jinja=True)


# Samples that depend on "now" or are documentation-style addresses cannot equal a computed value: checked by type.
_NOW_RELATIVE_KEYS = {"DAYS_LEFT", "EXPIRE_DATE", "JALALI_EXPIRE_DATE", "TIME_LEFT"}
_EXAMPLE_ONLY_KEYS = {"SERVER_IP", "SERVER_IPV6"}


@pytest.mark.parametrize(
    ("limits", "samples"),
    [
        ({"data_limit": 10 * 1024**3, "expire": datetime.now(UTC) + timedelta(days=12)}, SAMPLE_FORMAT_VARIABLES),
        # "∞" doesn't depend on "now", so this case has no now-relative keys and is checked in full below.
        ({"data_limit": None, "expire": None}, UNLIMITED_FORMAT_VARIABLES),
    ],
)
def test_samples_are_typed_like_the_variables_subscriptions_build(limits, samples):
    # Templates are checked against the samples, so they must not drift from what a subscription really gets.
    user = SimpleNamespace(
        username="sample_user",
        status=UserStatus.active,
        used_traffic=1024**3,  # matches SAMPLE_FORMAT_VARIABLES's DATA_USAGE/DATA_LEFT/USAGE_PERCENTAGE exactly
        on_hold_expire_duration=None,
        admin=SimpleNamespace(username="admin"),
        **limits,
    )
    built = setup_format_variables(user)
    expected = {key: value for key, value in samples.items() if key not in REQUEST_VARIABLES}
    assert built.keys() == expected.keys()

    type_only = expected.keys() & (_NOW_RELATIVE_KEYS | _EXAMPLE_ONLY_KEYS)
    assert {key: type(built[key]) for key in type_only} == {key: type(expected[key]) for key in type_only}
    assert {key: value for key, value in built.items() if key not in type_only} == {
        key: value for key, value in expected.items() if key not in type_only
    }


def _process_with_override(override: str, calls: list) -> None:
    """Runs a host whose inbound points at an Xray template override, and whose download sub-inbound is processed
    after it and overwrites PROTOCOL/TRANSPORT on the same shared dict."""
    download = SubscriptionInboundData(
        remark="dl",
        inbound_tag="dl",
        protocol="trojan",
        network="xhttp",
        address=["dl.example"],
        port=[80],
        tls_config=TLSConfig(),
        transport_config=XHTTPTransportConfig(),
    )
    main = SubscriptionInboundData(
        remark="main",
        inbound_tag="main",
        protocol="vless",
        network="tcp",
        address=["host.example"],
        port=[443],
        tls_config=TLSConfig(),
        transport_config=XHTTPTransportConfig(download_settings=download),
        subscription_templates={"xray": 1},
    )
    conf = XrayConfiguration()
    conf.add = lambda **kwargs: calls.append(kwargs)  # protocol handlers aren't the point of these tests
    user = SimpleNamespace(
        id=1,
        status=UserStatus.active,
        inbounds=["main", "dl"],
        proxy_settings=SimpleNamespace(dict=lambda: {"vless": {"id": "u"}, "trojan": {"password": "p"}}),
    )
    preparer = HostPreparer(user, {"PROTOCOL": "", "TRANSPORT": ""}, None, [main])
    process_inbounds_and_tags(
        user,
        conf,
        {"XRAY_SUBSCRIPTION_TEMPLATE": "{}"},
        preparer,
        preparer.host_refs(),
        xray_template_overrides={1: TemplateSource(override, True, 1)},
    )


def test_host_xray_override_sees_its_own_inbounds_protocol():
    # The main inbound's own override must not render with the sub-inbound's values.
    calls: list = []
    _process_with_override('{"outbounds": [], "protocol_seen": "{{ PROTOCOL }}"}', calls)

    assert len(calls) == 1
    assert json.loads(calls[0]["template_content"])["protocol_seen"] == "vless"


def test_host_xray_override_rendering_to_invalid_json_fails_loudly():
    # Serving the host with the default template instead would hide the broken override from everyone.
    with pytest.raises(TemplateRenderError):
        _process_with_override('{"outbounds": [], "protocol_seen": "{{ PROTOCOL }}}', [])


def _admin_with(client_templates: CRUDPermissions) -> AdminDetails:
    return AdminDetails(
        id=1,
        username="admin",
        role=AdminRoleData(
            id=1, name="role", is_owner=False, permissions=RolePermissions(client_templates=client_templates)
        ),
    )


@pytest.mark.asyncio
async def test_validate_endpoint_accepts_update_only_admins():
    from app.routers.client_template import _require_create_or_update

    update_only = _admin_with(CRUDPermissions(update=True))
    assert await _require_create_or_update(update_only) is update_only

    create_only = _admin_with(CRUDPermissions(create=True))
    assert await _require_create_or_update(create_only) is create_only

    with pytest.raises(HTTPException) as exc:
        await _require_create_or_update(_admin_with(CRUDPermissions()))
    assert exc.value.status_code == 403
