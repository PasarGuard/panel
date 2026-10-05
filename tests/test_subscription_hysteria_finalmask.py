import json
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.hosts import _prepare_subscription_inbound_data
from app.models.host import BaseHost
from app.models.subscription import SubscriptionInboundData
from app.subscription.clash import ClashMetaConfiguration
from app.subscription.links import StandardLinks
from app.subscription.singbox import SingBoxConfiguration

FINALMASK = {
    "udp": [{"type": "salamander", "settings": {"password": "obfs-secret"}}],
    "quicParams": {"udpHop": {"ports": "20000-20010", "interval": "30"}, "brutalUp": "50 mbps"},
}


@pytest.fixture
def hysteria_inbound(monkeypatch: pytest.MonkeyPatch):
    """Inbound config returned by the core manager for the test host."""
    inbound_config = {"protocol": "hysteria", "network": "tcp", "tls": "tls", "sni": ["cert.example.com"]}
    monkeypatch.setattr("app.core.hosts.core_manager.get_inbound_by_tag", AsyncMock(return_value=inbound_config))
    return inbound_config


async def _prepare(**host_fields) -> SubscriptionInboundData:
    """Prepare a Hysteria2 host the way HostManager does."""
    host = BaseHost(remark="hy2", address={"edge.example.com"}, port=443, inbound_tag="hy2", priority=0, **host_fields)
    inbound = await _prepare_subscription_inbound_data(host)
    # share.py picks one port per request from the prepared list
    return inbound.model_copy(update={"port": inbound.port[0]})


def _nats_round_trip(inbound: SubscriptionInboundData) -> SubscriptionInboundData:
    """Same JSON round trip as HostManager._persist_state / _load_state_from_cache."""
    return SubscriptionInboundData.model_validate(json.loads(json.dumps(inbound.model_dump())))


def _link_query(inbound: SubscriptionInboundData) -> dict[str, list[str]]:
    """Query parameters of the Hysteria2 share link."""
    links = StandardLinks()
    links.add("hy2", "edge.example.com", inbound, {"auth": "auth-password"})
    return parse_qs(urlparse(links.links[0]).query)


def _assert_builders_read_finalmask(inbound: SubscriptionInboundData):
    """Salamander and quicParams reach links, Clash Meta and sing-box."""
    query = _link_query(inbound)
    assert query["obfs"] == ["salamander"]
    assert query["obfs-password"] == ["obfs-secret"]
    assert query["mports"] == ["20000-20010"]

    meta = ClashMetaConfiguration()
    meta.add("hy2", "edge.example.com", inbound, {"auth": "auth-password"})
    node = meta.data["proxies"][0]
    assert node["obfs-password"] == "obfs-secret"
    assert node["up"] == "50 mbps"

    singbox = SingBoxConfiguration()
    singbox.add("hy2", "edge.example.com", inbound, {"auth": "auth-password"})
    outbound = singbox.config["outbounds"][-1]
    assert outbound["obfs"] == {"type": "salamander", "password": "obfs-secret"}
    assert outbound["hop_interval"] == "30s"


@pytest.mark.usefixtures("hysteria_inbound")
async def test_host_finalmask_is_prepared_with_xray_field_names():
    inbound = await _prepare(final_mask_settings=FINALMASK)

    assert inbound.finalmask == FINALMASK
    assert json.loads(inbound.finalmask_link) == FINALMASK


@pytest.mark.usefixtures("hysteria_inbound")
async def test_hysteria2_builders_read_host_finalmask():
    _assert_builders_read_finalmask(await _prepare(final_mask_settings=FINALMASK))


@pytest.mark.usefixtures("hysteria_inbound")
async def test_hysteria2_builders_read_host_finalmask_after_nats_cache_round_trip():
    _assert_builders_read_finalmask(_nats_round_trip(await _prepare(final_mask_settings=FINALMASK)))


async def test_hysteria2_builders_read_inbound_finalmask(hysteria_inbound):
    hysteria_inbound["finalmask"] = FINALMASK

    _assert_builders_read_finalmask(await _prepare())
