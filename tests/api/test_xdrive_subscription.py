"""Subscriptions for users with an Xray XDrive inbound."""

import base64
import json

import pytest

from app.models.subscription import (
    GRPCTransportConfig,
    KCPTransportConfig,
    QUICTransportConfig,
    SubscriptionInboundData,
    TCPTransportConfig,
    TLSConfig,
    WebSocketTransportConfig,
    XDriveTransportConfig,
    XHTTPTransportConfig,
)
from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_core,
    create_group,
    create_user,
    delete_core,
    delete_group,
    delete_user,
    unique_name,
)

XDRIVE_SETTINGS = {"remoteFolder": "pg-test", "service": "gdrive", "secrets": ["test-secret"], "segmentBytes": 65536}


def _core_config(xdrive_tag: str, tcp_tag: str) -> dict:
    return {
        "inbounds": [
            {
                "tag": xdrive_tag,
                "protocol": "vless",
                "port": 18443,
                "settings": {"clients": [], "decryption": "none"},
                "streamSettings": {"network": "xdrive", "xdriveSettings": XDRIVE_SETTINGS},
            },
            {
                "tag": tcp_tag,
                "protocol": "vless",
                "port": 18444,
                "settings": {"clients": [], "decryption": "none"},
                "streamSettings": {"network": "tcp"},
            },
        ],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
    }


@pytest.fixture
def xdrive_user(access_token):
    headers = auth_headers(access_token)
    xdrive_tag, tcp_tag = unique_name("xdrive_in"), unique_name("tcp_in")
    core = create_core(access_token, config=_core_config(xdrive_tag, tcp_tag))
    group = create_group(access_token, inbound_tags=[xdrive_tag, tcp_tag])
    user = create_user(access_token, group_ids=[group["id"]])
    remarks = {"xdrive": unique_name("xdhost"), "tcp": unique_name("tcphost")}
    host_ids = []
    for kind, tag in (("xdrive", xdrive_tag), ("tcp", tcp_tag)):
        host = {"remark": remarks[kind], "address": ["198.51.100.30"], "inbound_tag": tag, "priority": 1}
        if kind == "xdrive":
            # use_sni_as_host fills the transport's host; XDrive must still not emit it.
            host.update({"security": "tls", "sni": ["sni.example"], "use_sni_as_host": True})
        response = client.post("/api/host", headers=headers, json=host)
        assert response.status_code == 201, response.text
        host_ids.append(response.json()["id"])
    try:
        yield user, remarks
    finally:
        for host_id in host_ids:
            client.delete(f"/api/host/{host_id}", headers=headers)
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_xray_subscription_carries_xdrive_settings(xdrive_user):
    user, _ = xdrive_user
    response = client.get(f"{user['subscription_url']}/xray")
    assert response.status_code == 200, response.text

    streams = [
        outbound["streamSettings"]
        for config in response.json()
        for outbound in config.get("outbounds", [])
        if isinstance(outbound.get("streamSettings"), dict)
    ]
    xdrive_streams = [stream for stream in streams if stream.get("network") == "xdrive"]
    assert len(xdrive_streams) == 1
    # Only XDrive's own keys: the inherited empty path and host are not emitted.
    assert xdrive_streams[0]["xdriveSettings"] == XDRIVE_SETTINGS
    assert any(stream.get("network") in ("tcp", "raw") for stream in streams)


@pytest.mark.parametrize("client_type", ["links", "links_base64", "sing_box", "clash_meta"])
def test_formats_without_xdrive_skip_only_the_xdrive_host(xdrive_user, client_type):
    user, remarks = xdrive_user
    response = client.get(f"{user['subscription_url']}/{client_type}")
    assert response.status_code == 200, response.text

    body = response.text
    if client_type == "links_base64":
        body = base64.b64decode(body).decode()
    assert remarks["xdrive"] not in body
    assert remarks["tcp"] in body


@pytest.mark.parametrize("client_type", ["clash", "outline"])
def test_formats_without_vless_still_render(xdrive_user, client_type):
    # Neither format carries VLESS, so only the request succeeding is checked.
    user, remarks = xdrive_user
    response = client.get(f"{user['subscription_url']}/{client_type}")
    assert response.status_code == 200, response.text
    assert remarks["xdrive"] not in response.text


@pytest.mark.parametrize(
    "transport_config",
    [
        XDriveTransportConfig(remote_folder="pg-test", service="gdrive", secrets=["test-secret"]),
        TCPTransportConfig(path="/tcp", host=["tcp.example"]),
        QUICTransportConfig(path="/quic", host=["quic.example"]),
        GRPCTransportConfig(path="grpc", multi_mode=True),
        WebSocketTransportConfig(path="/ws", host=["ws.example"]),
        XHTTPTransportConfig(path="/xhttp", host=["xhttp.example"]),
        KCPTransportConfig(mtu=1350),
    ],
    ids=lambda config: type(config).__name__,
)
def test_host_cache_round_trip_keeps_transport_type(transport_config):
    data = SubscriptionInboundData(
        remark="r",
        inbound_tag="t",
        protocol="vless",
        port=[443],
        network="tcp",
        tls_config=TLSConfig(),
        transport_config=transport_config,
    )
    # The host cache stores plain model_dump() output; dropping None or default fields there
    # would let the union pick the wrong transport model.
    restored = SubscriptionInboundData.model_validate(json.loads(json.dumps(data.model_dump(mode="json"))))
    assert type(restored.transport_config) is type(transport_config)
    assert restored.transport_config == transport_config
