import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError

from app.core.hosts import HostManager, _prepare_subscription_inbound_data
from app.core.xray import XRayConfig
from app.models.host import BaseHost, FinalMask
from app.models.subscription import SubscriptionInboundData
from app.subscription.links import StandardLinks
from app.subscription.xray import XrayConfiguration

USER_ID = "11111111-1111-1111-1111-111111111111"

# Xray v26.10.21 "filter" mask: source IP filtering that only the server applies
TCP_FILTER = {"type": "filter", "settings": {"allowedSourceIPs": ["10.0.0.0/8"], "blockedSourceIPs": ["10.6.6.6"]}}
UDP_FILTER = {"type": "filter", "settings": {"blockedSourceIPs": ["192.0.2.0/24"]}}
FRAGMENT = {"type": "fragment", "settings": {"packets": "tlshello", "lengths": ["100-200"], "delays": ["10-20"]}}
NOISE = {"type": "noise", "settings": {"noise": [{"type": "str", "packet": "hello", "delay": "10-16"}]}}
QUIC_PARAMS = {"congestion": "bbr"}


def _xray_inbound(finalmask: dict) -> dict:
    """Inbound metadata as XRayConfig parses it from streamSettings.finalmask."""
    config = {
        "inbounds": [
            {
                "tag": "vless-in",
                "protocol": "vless",
                "port": 443,
                "settings": {"clients": [], "decryption": "none"},
                "streamSettings": {"network": "tcp", "finalmask": finalmask},
            }
        ],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
    }
    return XRayConfig(config).inbounds_by_tag["vless-in"]


@pytest.fixture
def inbound_finalmask(monkeypatch: pytest.MonkeyPatch):
    """Point the core manager at a parsed VLESS inbound that carries the given finalmask."""

    def use(finalmask: dict) -> dict:
        inbound = _xray_inbound(finalmask)
        monkeypatch.setattr("app.core.hosts.core_manager.get_inbound_by_tag", AsyncMock(return_value=inbound))
        return inbound

    return use


async def _prepare(**host_fields) -> SubscriptionInboundData:
    """Prepare a VLESS host the way HostManager does."""
    host = BaseHost(remark="vless", address={"edge.example.com"}, inbound_tag="vless-in", priority=0, **host_fields)
    inbound = await _prepare_subscription_inbound_data(host)
    return inbound.model_copy(update={"port": inbound.port[0]})


def _nats_round_trip(inbound: SubscriptionInboundData) -> SubscriptionInboundData:
    """Same JSON round trip as HostManager._persist_state / _load_state_from_cache."""
    return SubscriptionInboundData.model_validate(json.loads(json.dumps(inbound.model_dump())))


def _xray_stream_settings(inbound: SubscriptionInboundData) -> dict:
    xray = XrayConfiguration(xray_template_content=json.dumps({"outbounds": []}))
    xray.add("vless", "edge.example.com", inbound, {"id": USER_ID})
    return xray.config[0]["outbounds"][0]["streamSettings"]


def _link_query(inbound: SubscriptionInboundData) -> dict[str, list[str]]:
    links = StandardLinks()
    links.add("vless", "edge.example.com", inbound, {"id": USER_ID})
    return parse_qs(urlparse(links.links[0]).query)


async def test_inbound_filter_layers_stay_out_of_client_configs(inbound_finalmask):
    finalmask = {"tcp": [TCP_FILTER, FRAGMENT], "udp": [UDP_FILTER, NOISE], "quicParams": QUIC_PARAMS}
    inbound_config = inbound_finalmask(finalmask)
    original = deepcopy(inbound_config)
    expected = {"tcp": [FRAGMENT], "udp": [NOISE], "quicParams": QUIC_PARAMS}

    for inbound in (prepared := await _prepare(), _nats_round_trip(prepared)):
        # The rest of the mask is kept as is, in its original key and layer order
        assert json.dumps(inbound.finalmask) == json.dumps(expected)
        assert json.loads(inbound.finalmask_link)["tcp"][0]["type"] == "fragment"

        xray_mask = _xray_stream_settings(inbound)["finalmask"]
        assert [layer["type"] for layer in xray_mask["tcp"]] == ["fragment"]
        assert xray_mask["udp"] == [NOISE]
        assert xray_mask["quicParams"] == QUIC_PARAMS

        fm = json.loads(_link_query(inbound)["fm"][0])
        assert [layer["type"] for layer in fm["tcp"]] == ["fragment"]
        assert fm["udp"] == [NOISE]
        assert "filter" not in inbound.finalmask_link

    # The core manager's inbound (server config) keeps its filter layers
    assert inbound_config == original


async def test_inbound_with_only_filter_layers_gives_no_client_finalmask(inbound_finalmask):
    inbound_finalmask({"tcp": [TCP_FILTER], "udp": [UDP_FILTER]})

    inbound = await _prepare()

    assert inbound.finalmask is None
    assert inbound.finalmask_link is None
    assert "finalmask" not in _xray_stream_settings(inbound)
    assert "fm" not in _link_query(inbound)


@pytest.mark.parametrize("layer_type", ["Filter", " filter ", "FILTER"])
async def test_filter_type_match_ignores_case_and_spaces(inbound_finalmask, layer_type):
    inbound_finalmask({"tcp": [{**TCP_FILTER, "type": layer_type}, FRAGMENT]})

    inbound = await _prepare()

    assert inbound.finalmask == {"tcp": [FRAGMENT]}


async def test_filter_layers_leave_other_keys_when_both_lists_empty(inbound_finalmask):
    inbound_finalmask({"udp": [UDP_FILTER], "quicParams": QUIC_PARAMS})

    inbound = await _prepare()

    assert inbound.finalmask == {"quicParams": QUIC_PARAMS}
    assert _xray_stream_settings(inbound)["finalmask"] == {"quicParams": QUIC_PARAMS}


async def test_inbound_finalmask_without_filter_is_unchanged(inbound_finalmask):
    finalmask = {"tcp": [FRAGMENT], "udp": [NOISE], "quicParams": QUIC_PARAMS}
    inbound_finalmask(deepcopy(finalmask))

    inbound = await _prepare()

    assert json.dumps(inbound.finalmask) == json.dumps(finalmask)


async def test_host_finalmask_still_overrides_inbound_finalmask(inbound_finalmask):
    inbound_finalmask({"tcp": [TCP_FILTER, FRAGMENT], "udp": [UDP_FILTER]})
    host_mask = {"udp": [NOISE]}

    inbound = await _prepare(final_mask_settings=host_mask)

    assert inbound.finalmask == host_mask
    assert json.loads(inbound.finalmask_link) == host_mask
    assert _xray_stream_settings(inbound)["finalmask"] == host_mask


@pytest.mark.parametrize("key, layer", [("tcp", TCP_FILTER), ("udp", UDP_FILTER)])
def test_host_finalmask_rejects_server_only_filter(key, layer):
    # Hosts describe client-side masks, so the host model never stores a filter layer
    with pytest.raises(ValidationError):
        FinalMask.model_validate({key: [layer]})


class _FakeKV:
    def __init__(self, entries: dict[str, bytes]):
        self.entries = entries

    async def get(self, key: str):
        value = self.entries.get(key)
        return SimpleNamespace(value=value) if value is not None else None


async def test_host_snapshot_written_before_the_filter_fix_is_not_loaded():
    # Older releases stored prepared hosts (inbound filter layers included) under "state"
    manager = HostManager()
    manager._kv = _FakeKV({"state": b"{}"})
    assert await manager._load_state_from_cache() is False

    manager._kv = _FakeKV({HostManager.STATE_CACHE_KEY: b"{}"})
    assert await manager._load_state_from_cache() is True
