import json
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError

from app.core.hosts import _prepare_subscription_inbound_data
from app.models.host import BaseHost, FinalMask
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


UDPHOP = {
    "type": "udphop",
    "settings": {
        "mode": "intervalRemote",
        "interval": "10-60",
        "remoteIPs": ["203.0.113.0/24"],
        "remotePorts": "20000-20010",
    },
}
SALAMANDER = {"type": "salamander", "settings": {"password": "obfs-secret"}}
XICMP = {"type": "xicmp", "settings": {"ips": ["198.51.100.7"]}}


def _udphop_settings(**settings):
    """Validated settings of a single udphop layer."""
    layer = {"type": "udphop", "settings": {**UDPHOP["settings"], **settings}}
    return FinalMask.model_validate({"udp": [layer]}).udp[0].settings


def test_finalmask_accepts_udphop_with_xray_field_names():
    dumped = FinalMask.model_validate({"udp": [SALAMANDER, UDPHOP]}).model_dump(by_alias=True, exclude_none=True)

    assert dumped["udp"] == [SALAMANDER, UDPHOP]


def test_finalmask_udphop_mode_is_case_insensitive():
    assert _udphop_settings(mode="intervallocal,INTERVALREMOTE").mode == "intervallocal,INTERVALREMOTE"


@pytest.mark.parametrize("mode", ["random", "intervalRemote,", "intervalRemote, intervalLocal", "", None])
def test_finalmask_rejects_invalid_or_missing_udphop_mode(mode):
    with pytest.raises(ValidationError):
        _udphop_settings(mode=mode)


@pytest.mark.parametrize(
    ("interval", "expected"), [("", None), (None, None), (45, "45"), (" 5-10 ", "5-10"), ("2147483647", "2147483647")]
)
def test_finalmask_udphop_interval_is_optional_and_normalized(interval, expected):
    assert _udphop_settings(interval=interval).interval == expected


@pytest.mark.parametrize("interval", ["abc", "30s", "10-", "3", "1-60", 4, "۳۰", "2147483648", "30-4294967326"])
def test_finalmask_rejects_invalid_udphop_interval(interval):
    with pytest.raises(ValidationError):
        _udphop_settings(interval=interval)


def test_finalmask_udphop_normalizes_remote_ips_and_ports():
    settings = _udphop_settings(remoteIPs=["198.51.100.7", " ", "203.0.113.0/24"], remotePorts=[20000, " 20005-20010"])

    assert settings.remote_ips == ["198.51.100.7/32", "203.0.113.0/24"]
    assert settings.remote_ports == "20000,20005-20010"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("remoteIPs", ["not-an-ip"]),
        ("remoteIPs", [123, "198.51.100.7"]),
        ("remotePorts", "20000-x"),
        ("remotePorts", "20000-99999"),
        ("remotePorts", "0"),
        ("remotePorts", "20010-20000"),
        ("remotePorts", "۲۰۰۰۰"),
    ],
)
def test_finalmask_rejects_invalid_udphop_targets(field, value):
    with pytest.raises(ValidationError):
        _udphop_settings(**{field: value})


@pytest.mark.parametrize(
    ("udp", "error"),
    [
        ([UDPHOP, SALAMANDER], "udphop must be the last UDP layer and appear once"),
        ([UDPHOP, UDPHOP], "udphop must be the last UDP layer and appear once"),
        ([XICMP, UDPHOP], "udphop cannot be combined with xicmp"),
        ([UDPHOP, XICMP], "udphop cannot be combined with xicmp"),
        ([{"type": "udphop"}], "udphop needs settings with a mode"),
    ],
)
def test_finalmask_rejects_udphop_layer_combinations_xray_cannot_dial(udp, error):
    with pytest.raises(ValidationError, match=error):
        FinalMask.model_validate({"udp": udp})


@pytest.mark.usefixtures("hysteria_inbound")
async def test_hysteria2_link_passes_udphop_through_fm():
    query = _link_query(await _prepare(final_mask_settings={"udp": [SALAMANDER, UDPHOP]}))

    assert json.loads(query["fm"][0])["udp"] == [SALAMANDER, UDPHOP]
    assert query["obfs-password"] == ["obfs-secret"]
    # Hop ports for non-Xray clients stay under the admin's control in quicParams.udpHop
    assert "mports" not in query


# Port hopping without a udp mask: the shape a plain FinalMask | dict union turned back into a model
QUIC_ONLY_HOP = {"quicParams": {"udpHop": {"ports": "20000-20010", "interval": "30"}}}


def _build_hysteria2(inbound: SubscriptionInboundData) -> tuple[dict[str, list[str]], dict, dict]:
    """Share link query, Clash Meta proxy and sing-box outbound of one host."""
    meta = ClashMetaConfiguration()
    meta.add("hy2", "edge.example.com", inbound, {"auth": "auth-password"})
    singbox = SingBoxConfiguration()
    singbox.add("hy2", "edge.example.com", inbound, {"auth": "auth-password"})
    return _link_query(inbound), meta.data["proxies"][0], singbox.config["outbounds"][-1]


def _assert_builders_read_quic_only_hop(inbound: SubscriptionInboundData):
    """udpHop reaches every builder, and no obfs appears without a salamander layer."""
    query, node, outbound = _build_hysteria2(inbound)
    assert query["mports"] == ["20000-20010"]
    assert "obfs" not in query
    assert node["ports"] == "20000-20010"
    assert node["hop-interval"] == "30s"
    assert not node.get("obfs")
    assert outbound["server_ports"] == ["20000-20010"]
    assert outbound["hop_interval"] == "30s"
    assert "obfs" not in outbound


@pytest.mark.usefixtures("hysteria_inbound")
async def test_prepared_finalmask_stays_a_dict_with_xray_field_names():
    inbound = await _prepare(final_mask_settings=QUIC_ONLY_HOP)
    assert type(inbound.finalmask) is dict
    assert inbound.finalmask == QUIC_ONLY_HOP

    inbound.finalmask = FinalMask.model_validate(QUIC_ONLY_HOP)
    assert type(inbound.finalmask) is dict
    assert inbound.finalmask == QUIC_ONLY_HOP


@pytest.mark.usefixtures("hysteria_inbound")
async def test_hysteria2_builders_read_host_quic_params_without_udp_mask():
    _assert_builders_read_quic_only_hop(await _prepare(final_mask_settings=QUIC_ONLY_HOP))


@pytest.mark.usefixtures("hysteria_inbound")
async def test_hysteria2_builders_read_host_quic_params_without_udp_mask_after_nats_cache_round_trip():
    _assert_builders_read_quic_only_hop(_nats_round_trip(await _prepare(final_mask_settings=QUIC_ONLY_HOP)))


async def test_hysteria2_builders_read_inbound_quic_params_without_udp_mask(hysteria_inbound):
    hysteria_inbound["finalmask"] = QUIC_ONLY_HOP

    _assert_builders_read_quic_only_hop(await _prepare())


@pytest.mark.parametrize(
    ("finalmask", "brutal_up", "obfs"),
    [
        pytest.param({"quicParams": {"brutalUp": "50 mbps"}}, "50 mbps", None, id="brutal-only"),
        pytest.param(
            {"udp": [SALAMANDER], "quicParams": {"brutalUp": "50 mbps"}}, "50 mbps", "salamander", id="no-udphop"
        ),
        pytest.param({"quicParams": {}}, None, None, id="empty-quic-params"),
    ],
)
@pytest.mark.usefixtures("hysteria_inbound")
async def test_hysteria2_builders_accept_host_finalmask_without_udphop(finalmask, brutal_up, obfs):
    query, node, outbound = _build_hysteria2(await _prepare(final_mask_settings=finalmask))

    assert query.get("obfs") == ([obfs] if obfs else None)
    assert "mports" not in query
    assert not node.get("ports")
    assert node.get("up") == brutal_up
    assert "server_ports" not in outbound


@pytest.mark.parametrize(
    "finalmask",
    [
        pytest.param({"quicParams": {"udpHop": None}}, id="null-udphop"),
        pytest.param({"udp": [{"type": "salamander", "settings": None}], "quicParams": None}, id="null-sections"),
    ],
)
async def test_hysteria2_builders_accept_nulls_in_inbound_finalmask(hysteria_inbound, finalmask):
    # Core configs are free-form JSON, so optional sections may be written as null
    hysteria_inbound["finalmask"] = finalmask

    query, node, outbound = _build_hysteria2(await _prepare())

    assert "mports" not in query
    assert "obfs" not in query
    assert not node.get("ports")
    assert "server_ports" not in outbound
