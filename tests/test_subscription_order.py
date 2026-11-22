from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import unquote, urlsplit

import pytest

from app.db.models import UserStatus
from app.models.settings import Subscription
from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription import share


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("remark_template", "expected_remark"),
    [("{DATA_LEFT}", "42 GB"), ("{DATA_LEFT} • {PROTOCOL}/{TRANSPORT}", "42 GB • vless/tcp")],
)
async def test_grouped_links_reshuffle_and_keep_first_remark(monkeypatch, remark_template, expected_remark):
    def host(name, group, protocol="vless", inbound_tag="available"):
        return SubscriptionInboundData(
            remark=name,
            address=[f"{name}.example.com"],
            port=[443],
            protocol=protocol,
            inbound_tag=inbound_tag,
            network="tcp",
            transport_config=TCPTransportConfig(),
            tls_config=TLSConfig(),
            subscription_order_group=group,
        )

    hosts = [
        host("fixed-b", "fixed"),
        host("tunnel-a", "shuffle"),
        host("unassigned", None),
        host("excluded", "shuffle", inbound_tag="unavailable"),
        host("unsupported", "shuffle", protocol="mtproto"),
        host("fixed-a", "fixed"),
        host("tunnel-b", "shuffle"),
    ]
    user = SimpleNamespace(
        id=280,
        status=UserStatus.active,
        inbounds=["available"],
        proxy_settings=SimpleNamespace(
            dict=lambda: {"vless": {"id": "c90cff8e-d651-414e-8e83-1a187622d957"}, "mtproto": {"secret": "test"}}
        ),
    )

    monkeypatch.setattr(share.host_manager, "get_hosts", AsyncMock(return_value=dict(enumerate(hosts))))
    monkeypatch.setattr(
        share,
        "subscription_settings",
        AsyncMock(return_value=Subscription(rules=[], first_config_remark=remark_template)),
    )
    monkeypatch.setattr(share, "setup_format_variables", lambda *_: {"DATA_LEFT": "42 GB"})
    monkeypatch.setattr(
        share,
        "subscription_client_templates",
        AsyncMock(return_value={"USER_AGENT_TEMPLATE": "", "GRPC_USER_AGENT_TEMPLATE": ""}),
    )

    async def refresh():
        output = await share.generate_subscription(user, "links", False, randomize_order=True)
        links = [urlsplit(link) for link in output.splitlines()]
        return [(link.hostname, unquote(link.fragment)) for link in links]

    monkeypatch.setattr(share.random, "shuffle", lambda hosts: hosts.reverse())
    assert await refresh() == [
        ("tunnel-b.example.com", expected_remark),
        ("tunnel-a.example.com", "tunnel-a"),
        ("fixed-b.example.com", "fixed-b"),
        ("fixed-a.example.com", "fixed-a"),
        ("unassigned.example.com", "unassigned"),
    ]

    monkeypatch.setattr(share.random, "shuffle", lambda hosts: None)
    assert await refresh() == [
        ("tunnel-a.example.com", expected_remark),
        ("tunnel-b.example.com", "tunnel-b"),
        ("fixed-b.example.com", "fixed-b"),
        ("fixed-a.example.com", "fixed-a"),
        ("unassigned.example.com", "unassigned"),
    ]


def test_ungrouped_subscriptions_keep_legacy_order(monkeypatch):
    hosts = [SimpleNamespace(subscription_order_group=None) for _ in range(3)]
    monkeypatch.setattr(share.random, "shuffle", lambda hosts: hosts.reverse())
    assert share.order_subscription_hosts(hosts, False) == hosts
    assert share.order_subscription_hosts(hosts, True) == hosts[::-1]
