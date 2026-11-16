import certifi
import pytest
from PasarGuardNodeBridge import NodeAPIError, NodeType
from pydantic import ValidationError

from app.db.models import Node
from app.models.node import NodeCreate, NodeModify
from app.node import NodeManager
from app.node.bridge import create_node


def create_payload(**overrides):
    return {
        "name": "tls-node",
        "address": "node.example.com",
        "connection_type": "grpc",
        "api_key": "123e4567-e89b-12d3-a456-426614174000",
        "keep_alive": 60,
        "core_config_id": 1,
        "port": 62050,
        "api_port": 62051,
    } | overrides


@pytest.mark.parametrize("value", ["AB" * 32, ":".join(["aB"] * 32)])
def test_fingerprint_is_normalized(value):
    node = NodeCreate(**create_payload(certificate_sha256=value))
    assert node.certificate_sha256 == "ab" * 32
    assert node.server_ca == ""


@pytest.mark.parametrize("value", ["ab" * 31, "ab" * 33, "gg" * 32, "a:b" * 32, " ", "ab:" * 31 + "abcd"])
def test_malformed_fingerprint_rejected(value):
    with pytest.raises(ValidationError):
        NodeCreate(**create_payload(certificate_sha256=value))


def test_trust_defaults_and_empty_pem():
    assert NodeCreate(**create_payload()).server_ca == ""
    assert NodeCreate(**create_payload(server_ca=" \n\t")).server_ca == ""
    assert NodeCreate(**create_payload()).certificate_sha256 is None
    with pytest.raises(ValidationError):
        NodeCreate(**create_payload(server_ca="invalid PEM", certificate_sha256="ab" * 32))


@pytest.mark.parametrize("value", [None, ""])
def test_explicit_pin_clearing_preserves_presence(value):
    modify = NodeModify(certificate_sha256=value)
    assert modify.certificate_sha256 is None
    assert "certificate_sha256" in modify.model_fields_set
    assert "certificate_sha256" not in NodeModify(name="new name").model_fields_set


def test_both_fields_allowed_and_legacy_pem_retained():
    pem = certifi.contents().split("-----END CERTIFICATE-----", 1)[0].split("-----BEGIN CERTIFICATE-----", 1)[1]
    pem = "-----BEGIN CERTIFICATE-----" + pem + "-----END CERTIFICATE-----"
    node = NodeCreate(**create_payload(server_ca=pem, certificate_sha256="ab" * 32))
    assert node.server_ca == pem
    assert node.certificate_sha256 == "ab" * 32


def test_connection_signature_tracks_both_verification_fields():
    original = Node(**create_payload(server_ca="pem"))
    pinned = Node(**create_payload(server_ca="pem", certificate_sha256="ab" * 32))
    cleared = Node(**create_payload(server_ca=""))
    assert NodeManager._connection_signature(original) != NodeManager._connection_signature(pinned)
    assert NodeManager._connection_signature(original) != NodeManager._connection_signature(cleared)
    assert NodeManager()._create_node_kwargs(pinned)["certificate_sha256"] == "ab" * 32


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", [NodeType.grpc, NodeType.rest])
@pytest.mark.parametrize("policy", ["system", "pem", "pin", "both"])
async def test_bridge_011_constructs_all_verification_policies(transport, policy):
    pem = certifi.contents() if policy in ("pem", "both") else ""
    pin = "ab" * 32 if policy in ("pin", "both") else None
    node = create_node(
        transport,
        address="localhost",
        port=1,
        api_port=1,
        api_key=create_payload()["api_key"],
        server_ca=pem,
        certificate_sha256=pin,
    )
    try:
        assert node._tls_policy.server_ca == pem
        assert node._tls_policy.certificate_sha256 == pin
        assert node._json_client._base_url.startswith("https://")
    finally:
        await node.aclose()


@pytest.mark.asyncio
async def test_retired_bridge_closes_all_local_transports():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from app.node.bridge import _QueuedBatchSync

    bridge = SimpleNamespace(
        disconnect=AsyncMock(),
        _close_chan=Mock(),
        _client=SimpleNamespace(close=AsyncMock()),
        _json_client=SimpleNamespace(close=AsyncMock()),
    )
    await _QueuedBatchSync.aclose(bridge)
    bridge.disconnect.assert_awaited_once()
    bridge._close_chan.assert_called_once()
    bridge._client.close.assert_awaited_once()
    bridge._json_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_rejected_policy_retires_previous_connection(monkeypatch):
    from unittest.mock import AsyncMock

    manager = NodeManager()
    previous = AsyncMock()
    manager._nodes[1] = previous
    manager._node_signatures[1] = ("old-policy",)
    monkeypatch.setattr("app.node.ensure_bridge_memory", AsyncMock())
    monkeypatch.setattr("app.node.create_node", lambda **kwargs: (_ for _ in ()).throw(NodeAPIError(-1, "bad policy")))
    node = Node(**create_payload(server_ca="pem", certificate_sha256="ab" * 32))
    node.id = 1
    with pytest.raises(NodeAPIError):
        await manager.update_node(node)
    assert 1 not in manager._nodes
    assert 1 not in manager._node_signatures
    previous.aclose.assert_awaited_once()
    previous.stop.assert_not_awaited()
