"""Subscription format fields: strict on input, stored values load and are neutralised when rendered."""

import time
import tracemalloc

import pytest
from pydantic import ValidationError

from app.models.admin import AdminContactInfo, AdminModify
from app.models.settings import (
    SETTINGS_INPUT_CONTEXT,
    Application,
    ConfigFormat,
    DownloadLink,
    General,
    Language,
    SubRule,
    Subscription,
)
from app.operation.subscription import SubscriptionOperation

# --- Application import_url ----------------------------------------------------------------------


def _application(import_url: str) -> Application:
    return Application.model_validate(
        {"name": "App", "platform": "android", "download_links": [], "import_url": import_url},
        context=SETTINGS_INPUT_CONTEXT,
    )


@pytest.mark.parametrize(
    "import_url",
    ["happ://add/{url}{USERNAME:>999999999}", "happ://add/{url}{USERNAME.x}", "happ://add/{url}{USERNAME[0]}"],
)
def test_import_url_rejects_oversized_widths_and_attribute_fields(import_url):
    with pytest.raises(ValidationError):
        _application(import_url)


def test_import_url_keeps_working_for_legitimate_values():
    assert _application("happ://add/{url}").import_url == "happ://add/{url}"
    assert _application("").import_url == ""


@pytest.mark.parametrize("stored", ["x://{url}{USERNAME:>999999999}", "x://{url}{USERNAME.x}", "x://{url}{0}"])
def test_stored_bad_import_url_is_served_raw_instead_of_failing(stored):
    app = Application.model_construct(
        name="App", platform="android", download_links=[], import_url=stored, show_when_hwid_enabled=False
    )
    started = time.perf_counter()
    rendered = SubscriptionOperation(operator_type=None)._make_apps_import_urls(
        [app], {"url": "https://panel/sub/t", "USERNAME": "bob"}, is_hwid_enabled=False
    )
    assert rendered[0].import_url == stored
    assert time.perf_counter() - started < 1


def test_import_url_is_formatted_with_the_subscription_url():
    app = _application("happ://add/{url}")
    rendered = SubscriptionOperation(operator_type=None)._make_apps_import_urls(
        [app], {"url": "https://panel/sub/t"}, is_hwid_enabled=False
    )
    assert rendered[0].import_url == "happ://add/https://panel/sub/t"


# --- Custom variables: an oversized width is refused before it is ever formatted -------------------

_WIDE_VARIABLE = {"key": "B", "value": "{USERNAME:>999999999}"}


def _peak_mb(fn) -> float:
    tracemalloc.start()
    try:
        fn()
        return tracemalloc.get_traced_memory()[1] / 1024**2
    finally:
        tracemalloc.stop()


def _refused(fn):
    def run():
        with pytest.raises(ValidationError):
            fn()

    return run


@pytest.mark.parametrize(
    "parse",
    [
        _refused(
            lambda: General.model_validate({"custom_variables": [_WIDE_VARIABLE]}, context=SETTINGS_INPUT_CONTEXT)
        ),
        _refused(lambda: AdminModify.model_validate({"custom_variables": [_WIDE_VARIABLE]})),
        # Request bodies are parsed without the input context before the operation re-validates them.
        lambda: General.model_validate({"custom_variables": [_WIDE_VARIABLE]}),
        # A value stored before the check loads as raw text on every subscription of that admin.
        lambda: AdminContactInfo.model_validate({"username": "admin", "custom_variables": [_WIDE_VARIABLE]}),
    ],
)
def test_oversized_custom_variable_is_never_formatted(parse):
    assert _peak_mb(parse) < 100


@pytest.mark.parametrize("value", ["{USERNAME[0]}", "{USERNAME.foo}", "{USERNAME"])
def test_custom_variable_with_bad_fields_is_refused_on_input_and_loads_raw(value):
    variable = {"key": "B", "value": value}
    with pytest.raises(ValidationError):
        General.model_validate({"custom_variables": [variable]}, context=SETTINGS_INPUT_CONTEXT)
    with pytest.raises(ValidationError):
        AdminModify.model_validate({"custom_variables": [variable]})
    loaded = AdminContactInfo.model_validate({"username": "admin", "custom_variables": [variable]})
    assert loaded.custom_variables[0].value == value


# --- Subscription settings: format widths, link schemes and client rules -------------------------


def _input(model, **data):
    return model.model_validate(data, context=SETTINGS_INPUT_CONTEXT)


def test_subscription_rejects_oversized_format_spec():
    with pytest.raises(ValidationError):
        _input(Subscription, profile_title="{USERNAME:>999999999}", rules=[])
    assert _input(Subscription, profile_title="{USERNAME.x}", rules=[]).profile_title == "{USERNAME.x}"


def test_download_link_rejects_dangerous_schemes():
    with pytest.raises(ValidationError):
        _input(DownloadLink, name="x", url="javascript:alert(1)", language=Language.EN)
    link = _input(DownloadLink, name="x", url="https://example.com/app", language=Language.EN)
    assert link.url == "https://example.com/app"


def test_sub_rule_rejects_invalid_or_oversized_regex():
    with pytest.raises(ValidationError):
        _input(SubRule, pattern="(", target=ConfigFormat.links)
    with pytest.raises(ValidationError):
        _input(SubRule, pattern="a" * 513, target=ConfigFormat.links)
    assert _input(SubRule, pattern=".*Clash.*", target=ConfigFormat.links).pattern == ".*Clash.*"


def test_detect_client_rule_skips_invalid_stored_patterns():
    broken = SubRule.model_construct(pattern="(", target=ConfigFormat.links, response_headers={})
    good = SubRule(pattern=".*Clash.*", target=ConfigFormat.clash_meta)

    assert SubscriptionOperation.detect_client_rule("Clash/1.0", [broken, good]).target == ConfigFormat.clash_meta


def test_subscription_link_urls_reject_dangerous_schemes():
    with pytest.raises(ValidationError):
        _input(Subscription, announce_url="javascript:alert(1)", rules=[])
    assert _input(Subscription, announce_url="https://example.com", rules=[]).announce_url == "https://example.com"
