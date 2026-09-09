from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.settings import ConfigFormat, SubRule, Subscription
from app.operation import OperatorType
from app.operation.subscription import SubscriptionOperation


def operation(monkeypatch, rules):
    result = SubscriptionOperation(OperatorType.API)
    monkeypatch.setattr(result, "get_validated_user_by_id", AsyncMock(return_value=object()))
    monkeypatch.setattr(result, "validated_user", AsyncMock(return_value=SimpleNamespace(status="active")))
    monkeypatch.setattr(
        "app.operation.subscription.subscription_settings", AsyncMock(return_value=Subscription(rules=rules))
    )
    monkeypatch.setattr(result, "_get_rule_response_header_variables", AsyncMock(return_value={}))
    return result


@pytest.mark.asyncio
async def test_preview_uses_first_user_agent_match_without_side_effects(monkeypatch):
    rules = [
        SubRule(pattern="^Other", target=ConfigFormat.block),
        SubRule(pattern="^Happ", target=ConfigFormat.xray, ui_application="Happ"),
    ]
    result = operation(monkeypatch, rules)
    monkeypatch.setattr(
        result,
        "fetch_rule_config",
        AsyncMock(return_value=('{"outbounds":[]}', "application/json", ConfigFormat.xray, None)),
    )
    monkeypatch.setattr(
        "app.operation.subscription.subscription_client_templates",
        AsyncMock(return_value={"XRAY_SUBSCRIPTION_TEMPLATE": "cached"}),
    )
    monkeypatch.setattr(
        "app.operation.subscription.get_client_templates",
        AsyncMock(return_value=([SimpleNamespace(id=7, name="Default", content="cached", is_default=True)], 1)),
    )
    preview = await result.user_subscription_rule_preview_by_id(None, 1, SimpleNamespace(), "Happ/2")
    assert preview["matched_rule"]["index"] == 1
    assert preview["matched_rule"]["ui_application"] == "Happ"
    assert preview["source"] == {"kind": "default_template", "id": 7, "name": "Default"}
    assert preview["content"] == '{"outbounds":[]}'


@pytest.mark.asyncio
async def test_preview_no_match_does_not_generate(monkeypatch):
    result = operation(monkeypatch, [SubRule(pattern="^Happ", target=ConfigFormat.xray)])
    generate = AsyncMock()
    monkeypatch.setattr(result, "fetch_rule_config", generate)
    preview = await result.user_subscription_rule_preview_by_id(None, 1, SimpleNamespace(), "Other")
    assert preview["matched_rule"] is None
    generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_preview_names_explicit_native_template(monkeypatch):
    rule = SubRule(pattern="^Happ", target=ConfigFormat.xray, template_id=41)
    result = operation(monkeypatch, [rule])
    template = SimpleNamespace(id=41, name="Happ tuned", template_type="xray_subscription", content="{}")
    monkeypatch.setattr(
        result,
        "fetch_rule_config",
        AsyncMock(return_value=("{}", "application/json", ConfigFormat.xray, None)),
    )
    preview = await result.user_subscription_rule_preview_by_id(
        None, 1, SimpleNamespace(), "Happ", template_overrides={41: template}
    )
    assert preview["source"] == {"kind": "native_template", "id": 41, "name": "Happ tuned"}


@pytest.mark.asyncio
async def test_happ_headers_follow_owned_precedence(monkeypatch):
    rule = SubRule(
        pattern=".*",
        target="links",
        response_headers={"custom": "kept"},
        happ_routing={"template_id": 7, "transport": "header", "enabled": False},
    )
    settings = Subscription(rules=[rule], response_headers={"RoUtInG": "old", "ROUTING-ENABLE": "1"})
    result = operation(monkeypatch, [rule])
    templates = {7: SimpleNamespace(id=7, name="route", template_type="happ_routing", content='{"Name":"x"}')}
    headers = await result.rule_response_headers(None, rule, settings, {}, templates)
    assert headers["custom"] == "kept"
    assert headers["routing"].startswith("happ://routing/onadd/")
    assert headers["routing-enable"] == "0"
    assert "RoUtInG" not in headers and "ROUTING-ENABLE" not in headers


@pytest.mark.asyncio
@pytest.mark.parametrize("headers_only", [False, True])
async def test_automatic_paths_reject_invalid_base_response_headers(monkeypatch, headers_only):
    rule = SubRule(pattern=".*", target="xray")
    settings = Subscription(rules=[rule])
    result = SubscriptionOperation(OperatorType.API)
    db_user = SimpleNamespace(admin=None, id=1, hwid_limit=0)
    monkeypatch.setattr("app.operation.subscription.subscription_settings", AsyncMock(return_value=settings))
    monkeypatch.setattr(result, "get_validated_sub", AsyncMock(return_value=db_user))
    monkeypatch.setattr(result, "validated_user", AsyncMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(result, "validate_and_register_hwid", AsyncMock())
    monkeypatch.setattr("app.operation.subscription.user_sub_update", AsyncMock())
    monkeypatch.setattr(
        result,
        "fetch_rule_config",
        AsyncMock(return_value=("{}", "application/json", ConfigFormat.xray, None)),
    )
    monkeypatch.setattr(result, "create_response_headers", lambda *_args, **_kwargs: {"support-url": "bad\r\nvalue"})
    monkeypatch.setattr(result, "_get_rule_response_header_variables", AsyncMock(return_value={}))
    monkeypatch.setattr(result, "rule_response_headers", AsyncMock(return_value={}))

    with pytest.raises(HTTPException) as exc:
        if headers_only:
            await result.user_subscription_headers(None, "token", user_agent="Client")
        else:
            await result.user_subscription(None, "token", user_agent="Client")
    assert exc.value.status_code == 400
