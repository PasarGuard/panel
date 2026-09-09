import asyncio
import json

import pytest

from app.subscription.client_diagnostics import (
    collect_preview_exceptions,
    diagnose_client_body,
    record_preview_exception,
)


def diagnose(document, config_format="xray"):
    return diagnose_client_body(json.dumps(document), config_format)


def test_xray_reference_checks_are_per_document():
    valid = {
        "outbounds": [{"tag": "proxy-de-1"}, {"tag": "direct"}],
        "routing": {
            "balancers": [{"tag": "automatic", "selector": ["absent-", "proxy-"], "fallbackTag": "direct"}],
            "rules": [{"balancerTag": "automatic"}, {"outboundTag": "direct"}],
        },
    }
    assert diagnose([valid]) == []
    errors = diagnose([valid, {"outbounds": [], "routing": valid["routing"]}])
    assert len(errors) == 3
    assert all(error.startswith("configs[1].") for error in errors)


def test_singbox_nested_routes_groups_and_endpoints():
    document = {
        "outbounds": [{"type": "selector", "tag": "select", "outbounds": ["wg"]}],
        "endpoints": [{"tag": "wg"}],
        "route": {"final": "select", "rules": [{"type": "logical", "rules": [{"outbound": "wg"}]}]},
    }
    assert diagnose(document, "sing_box") == []
    document["endpoints"] = []
    document["route"]["final"] = "missing"
    assert len(diagnose(document, "sing_box")) == 3


@pytest.mark.parametrize("config_format", ["clash", "clash_meta"])
def test_clash_reference_checks_do_not_echo_values(config_format):
    document = {
        "proxy-providers": {"remote": {}},
        "rule-providers": {"private": {}},
        "proxy-groups": [{"name": "Proxy", "proxies": ["absent"], "use": ["absent"]}],
        "rules": ["RULE-SET,absent,absent,no-resolve"],
    }
    errors = diagnose(document, config_format)
    assert len(errors) == 4
    assert not any("absent" in error for error in errors)


def test_parse_failure_and_unhandled_formats_are_safe():
    assert diagnose_client_body("{{ broken", "clash") == [
        "Rendered configuration could not be parsed for reference checks."
    ]
    assert diagnose_client_body(b"\xff", "xray")
    assert diagnose_client_body("vless://not-inspected", "links") == []


@pytest.mark.asyncio
async def test_exception_trace_is_request_scoped_and_restored():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def first():
        with collect_preview_exceptions() as exceptions:
            record_preview_exception("first")
            entered.set()
            await release.wait()
            assert exceptions == ["first"]
        return exceptions

    async def second():
        await entered.wait()
        with collect_preview_exceptions() as exceptions:
            record_preview_exception("second")
            release.set()
            await asyncio.sleep(0)
            assert exceptions == ["second"]
        return exceptions

    assert await asyncio.gather(first(), second()) == [["first"], ["second"]]
