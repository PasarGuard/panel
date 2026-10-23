"""`hosts` in client templates: every host, with a lazily built outbound tagged <tag_prefix>-<id>."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db.models import UserStatus
from app.models.client_template import TemplateSource
from app.models.proxy import ProxyTable
from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription import config_cache
from app.subscription.share import TemplateRenderError, generate_subscription

USER_UUID = "11111111-1111-1111-1111-111111111111"

XRAY_TEMPLATE = """{
  "outbounds": [
    {% for h in hosts if h.tag_prefix %}{{ h.outbounds | map('tojson') | join(',') }},{% endfor %}
    {"protocol": "freedom", "tag": "DIRECT"}
  ],
  "routing": {
    "balancers": [{"tag": "de", "selector": ["de-"]}],
    "rules": [{"type": "field", "ip": ["geoip:de"], "balancerTag": "de"}]
  }
}"""


def make_host(host_id: int, remark: str, *, tag_prefix=None, is_disabled=False, fragment=False):
    return SubscriptionInboundData(
        id=host_id,
        remark=remark,
        inbound_tag="in1",
        protocol="vless",
        address=[f"h{host_id}.example"],
        port=[443],
        network="tcp",
        tls_config=TLSConfig(tls="tls", sni=["sni.example"]),
        transport_config=TCPTransportConfig(path="", host=[]),
        fragment_settings={"xray": {"packets": "tlshello", "length": "100-200", "interval": "10-20"}}
        if fragment
        else None,
        tag_prefix=tag_prefix,
        is_disabled=is_disabled,
        priority=host_id,
    )


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch):
    config_cache.clear_sub_config_cache()
    monkeypatch.setattr(
        "app.subscription.share.subscription_settings",
        AsyncMock(return_value=SimpleNamespace(custom_variables=[])),
    )
    set_templates(monkeypatch, XRAY_SUBSCRIPTION_TEMPLATE=XRAY_TEMPLATE)
    monkeypatch.setattr("app.subscription.share.subscription_xray_templates", AsyncMock(return_value={}))
    yield
    config_cache.clear_sub_config_cache()


def set_templates(monkeypatch: pytest.MonkeyPatch, **templates: str):
    values = {
        "USER_AGENT_TEMPLATE": TemplateSource('{"list": []}', False, 1),
        "GRPC_USER_AGENT_TEMPLATE": TemplateSource('{"list": []}', False, 2),
    }
    values.update({key: TemplateSource(content, True, 3) for key, content in templates.items()})
    monkeypatch.setattr("app.subscription.share.subscription_client_templates", AsyncMock(return_value=values))


def set_hosts(monkeypatch: pytest.MonkeyPatch, hosts: list[SubscriptionInboundData]):
    monkeypatch.setattr(
        "app.subscription.share.host_manager",
        SimpleNamespace(get_all_hosts=AsyncMock(return_value={h.id: h for h in hosts})),
    )


def make_user():
    return SimpleNamespace(
        id=1,
        username="alice",
        status=UserStatus.active,
        inbounds=["in1"],
        data_limit=None,
        used_traffic=0,
        expire=None,
        on_hold_expire_duration=None,
        admin=None,
        proxy_settings=ProxyTable.model_validate({"vless": {"id": USER_UUID}}),
    )


async def render_xray(monkeypatch, hosts):
    set_hosts(monkeypatch, hosts)
    return json.loads(await generate_subscription(make_user(), "xray", False))


@pytest.mark.asyncio
async def test_tagged_hosts_are_embedded_with_unique_tags(monkeypatch):
    configs = await render_xray(
        monkeypatch,
        [make_host(1, "NL"), make_host(2, "DE 1", tag_prefix="de"), make_host(3, "DE 2", tag_prefix="de")],
    )

    # Tagged hosts are profiles of their own too, unless disabled
    assert [config["remarks"] for config in configs] == ["NL", "DE 1", "DE 2"]
    tags = [o["tag"] for o in configs[0]["outbounds"]]
    # Untagged hosts are not built unless a template asks
    assert tags == ["proxy", "de-2", "de-3", "DIRECT"]
    de_outbound = configs[0]["outbounds"][1]
    assert de_outbound["settings"]["vnext"][0]["address"] == "h2.example"
    assert de_outbound["settings"]["vnext"][0]["users"][0]["id"] == USER_UUID


@pytest.mark.asyncio
async def test_disabled_hosts_are_available_to_templates_but_not_listed(monkeypatch):
    configs = await render_xray(
        monkeypatch,
        [make_host(1, "NL"), make_host(2, "DE hidden", tag_prefix="de", is_disabled=True)],
    )

    assert [config["remarks"] for config in configs] == ["NL"]
    assert "de-2" in [o["tag"] for o in configs[0]["outbounds"]]


@pytest.mark.asyncio
async def test_dialer_outbounds_get_unique_tags(monkeypatch):
    configs = await render_xray(
        monkeypatch,
        [make_host(1, "NL"), make_host(2, "DE", tag_prefix="de", fragment=True)],
    )

    outbounds = {o["tag"]: o for o in configs[0]["outbounds"]}
    assert "dialer-de-2" in outbounds
    assert [tag for tag in outbounds if tag.startswith("de-")] == ["de-2"]
    assert outbounds["de-2"]["streamSettings"]["sockopt"]["dialerProxy"] == "dialer-de-2"


@pytest.mark.asyncio
async def test_template_can_look_a_host_up_by_prefix(monkeypatch):
    template = (
        '{"outbounds": [{"protocol": "freedom", "tag": "DIRECT"}],'
        ' "routing": {"rules": [{"type": "field", "ip": ["geoip:de"],'
        " \"outboundTag\": \"{{ (hosts | selectattr('tag_prefix', 'eq', 'de') | first).tag }}\"}]}}"
    )
    set_templates(monkeypatch, XRAY_SUBSCRIPTION_TEMPLATE=template)
    configs = await render_xray(monkeypatch, [make_host(1, "NL"), make_host(7, "DE", tag_prefix="de")])

    assert configs[0]["routing"]["rules"][0]["outboundTag"] == "de-7"


@pytest.mark.asyncio
async def test_host_remark_matches_the_subscription_entry(monkeypatch):
    monkeypatch.setattr(
        "app.subscription.share.subscription_settings",
        AsyncMock(return_value=SimpleNamespace(custom_variables=[{"key": "LABEL", "value": "{PROTOCOL}-{USERNAME}"}])),
    )
    template = "{% for h in hosts %}{{ h.remark }};{% endfor %}"
    set_templates(monkeypatch, CLASH_SUBSCRIPTION_TEMPLATE=template)
    set_hosts(monkeypatch, [make_host(1, "{LABEL} NL"), make_host(2, "{LABEL} DE", is_disabled=True)])

    assert await generate_subscription(make_user(), "clash", False) == "vless-alice NL;vless-alice DE;"


@pytest.mark.asyncio
async def test_broken_host_override_fails_the_subscription(monkeypatch):
    monkeypatch.setattr(
        "app.subscription.share.subscription_xray_templates",
        AsyncMock(return_value={5: TemplateSource('{"outbounds": {{ NOPE.x() }}}', True, 5)}),
    )
    host = make_host(1, "NL")
    host.subscription_templates = {"xray": 5}

    with pytest.raises(TemplateRenderError, match="template 5 failed"):
        await render_xray(monkeypatch, [host])


@pytest.mark.asyncio
async def test_host_without_access_is_not_available(monkeypatch):
    template = "{% for h in hosts %}{{ h.tag }}={{ h.available }};{% endfor %}"
    set_templates(monkeypatch, CLASH_SUBSCRIPTION_TEMPLATE=template)
    set_hosts(monkeypatch, [make_host(1, "NL"), make_host(2, "DE", tag_prefix="de")])
    user = make_user()
    user.inbounds = []

    assert await generate_subscription(user, "clash", False) == "out-1=False;de-2=False;"


def test_validation_samples_hosts_and_catches_the_unavailable_one():
    from app.models.client_template import ClientTemplateType
    from app.operation.client_template import InvalidTemplateContent, check_template_content

    lookup = '{"inbounds": [{"tag": "in"}], "outbounds": [{"tag": "{{ (hosts | selectattr(\'tag_prefix\', \'eq\', \'de\') | first).tag }}"}]}'
    check_template_content(ClientTemplateType.xray_subscription, lookup, ["x"], ["de"], use_jinja=True)
    with pytest.raises(InvalidTemplateContent):
        check_template_content(ClientTemplateType.xray_subscription, lookup, use_jinja=True)

    unguarded = (
        '{"inbounds": [{"tag": "in"}], "outbounds": [{% for h in hosts %}{{ h.outbounds | map("tojson") | join(",") }},{% endfor %}'
        '{"tag": "DIRECT"}]}'
    )
    with pytest.raises(InvalidTemplateContent):
        check_template_content(ClientTemplateType.xray_subscription, unguarded, use_jinja=True)
    guarded = unguarded.replace("{% for h in hosts %}", "{% for h in hosts if h.available %}")
    check_template_content(ClientTemplateType.xray_subscription, guarded, use_jinja=True)


@pytest.mark.asyncio
async def test_hosts_restricted_to_other_statuses_are_not_available(monkeypatch):
    template = "{% for h in hosts %}{{ h.tag }}={{ h.available }};{% endfor %}"
    set_templates(monkeypatch, CLASH_SUBSCRIPTION_TEMPLATE=template)
    expired_only = make_host(2, "renew")
    expired_only.status = [UserStatus.expired]
    set_hosts(monkeypatch, [make_host(1, "NL"), expired_only])

    result = await generate_subscription(make_user(), "clash", False)

    assert result == "out-1=True;out-2=False;"


@pytest.mark.asyncio
async def test_the_host_manager_lists_disabled_hosts_only_when_asked():
    from app.core.hosts import HostManager

    manager = HostManager()
    manager._hosts = {1: make_host(1, "NL"), 2: make_host(2, "off", is_disabled=True)}

    assert list(await manager.get_hosts()) == [1]
    assert list(await manager.get_all_hosts()) == [1, 2]


@pytest.mark.asyncio
async def test_identical_requests_arriving_together_share_one_build(monkeypatch):
    import asyncio

    from app.templates.pool import subscription_pool

    set_hosts(monkeypatch, [make_host(1, "NL")])
    builds = []
    run = subscription_pool.run

    async def counting(func, *args):
        builds.append(1)
        return await run(func, *args)

    monkeypatch.setattr(subscription_pool, "run", counting)

    results = await asyncio.gather(*(generate_subscription(make_user(), "xray", False) for _ in range(20)))

    assert len(builds) == 1
    assert len(set(results)) == 1


@pytest.mark.asyncio
async def test_share_links_do_not_depend_on_the_xray_template(monkeypatch):
    set_templates(monkeypatch, XRAY_SUBSCRIPTION_TEMPLATE='{"outbounds": {{ NOPE.x() }}}')
    set_hosts(monkeypatch, [make_host(1, "NL")])

    assert "vless://" in await generate_subscription(make_user(), "links", False)
