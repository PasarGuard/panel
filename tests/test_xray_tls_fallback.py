import datetime
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.core.xray import XRayConfig

PARENT_TAG = "vless-tls"
CHILD_TAG = "vless-ws"
SERVER_NAME = "fallback.example.com"
NODE_CERT_FILE = "/opt/certs/missing/fullchain.pem"
NODE_KEY_FILE = "/opt/certs/missing/privkey.pem"


def _write_self_signed(directory: Path) -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, SERVER_NAME)])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(SERVER_NAME)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path = directory / "fullchain.pem"
    key_path = directory / "privkey.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return str(cert_path), str(key_path)


def _parent_inbound(certificates: list[dict[str, Any]], child_ports: list[int]) -> dict[str, Any]:
    return {
        "tag": PARENT_TAG,
        "protocol": "vless",
        "listen": "0.0.0.0",
        "port": 443,
        "settings": {
            "clients": [],
            "decryption": "none",
            "fallbacks": [{"dest": port} for port in child_ports],
        },
        "streamSettings": {
            "network": "tcp",
            "security": "tls",
            "tlsSettings": {"serverName": SERVER_NAME, "certificates": certificates},
        },
    }


def _child_inbound(tag: str, port: int) -> dict[str, Any]:
    return {
        "tag": tag,
        "protocol": "vless",
        "listen": "127.0.0.1",
        "port": port,
        "settings": {"clients": [], "decryption": "none"},
        "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/ws"}},
    }


def _config(inbounds: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "inbounds": inbounds,
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
    }


def _node_served_certificate() -> dict[str, Any]:
    return {"serveOnNode": True, "certificateFile": NODE_CERT_FILE, "keyFile": NODE_KEY_FILE}


def _panel_certificate(cert_path: str, key_path: str) -> dict[str, str]:
    return {"certificateFile": cert_path, "keyFile": key_path}


def _parent_certificates(cfg: XRayConfig) -> list[dict[str, Any]]:
    return cfg.get_inbound(PARENT_TAG)["streamSettings"]["tlsSettings"]["certificates"]


def _emitted_inbounds(cfg: XRayConfig) -> list[dict[str, Any]]:
    return json.loads(cfg.to_str())["inbounds"]


def _emitted_parent(cfg: XRayConfig) -> dict[str, Any]:
    return next(inbound for inbound in _emitted_inbounds(cfg) if inbound["tag"] == PARENT_TAG)


@pytest.mark.parametrize("parent_first", [True, False])
def test_node_served_certificate_keeps_files_in_parent_regardless_of_order(parent_first: bool) -> None:
    parent = _parent_inbound([_node_served_certificate()], [8080])
    child = _child_inbound(CHILD_TAG, 8080)
    inbounds = [parent, child] if parent_first else [child, parent]

    cfg = XRayConfig(_config(inbounds))

    certificate = _parent_certificates(cfg)[0]
    assert certificate["certificateFile"] == NODE_CERT_FILE
    assert certificate["keyFile"] == NODE_KEY_FILE
    assert "serveOnNode" not in certificate
    assert "certificate" not in certificate
    assert "key" not in certificate
    assert cfg._inbounds_by_tag[f"{CHILD_TAG}<=>{PARENT_TAG}"]["sni"] == [SERVER_NAME]


def test_node_served_certificate_with_two_children_is_not_contaminated() -> None:
    parent = _parent_inbound([_node_served_certificate()], [8080, 8081])
    children = [_child_inbound("vless-ws-a", 8080), _child_inbound("vless-ws-b", 8081)]

    cfg = XRayConfig(_config([*children, parent]))

    certificate = _parent_certificates(cfg)[0]
    assert certificate["certificateFile"] == NODE_CERT_FILE
    assert "serveOnNode" not in certificate
    assert "certificate" not in certificate
    assert "key" not in certificate
    assert cfg._inbounds_by_tag["vless-ws-a<=>vless-tls"]["sni"] == [SERVER_NAME]
    assert cfg._inbounds_by_tag["vless-ws-b<=>vless-tls"]["sni"] == [SERVER_NAME]


@pytest.mark.parametrize("parent_first", [True, False])
def test_panel_certificate_is_inlined_once_in_both_orders(tmp_path: Path, parent_first: bool) -> None:
    cert_path, key_path = _write_self_signed(tmp_path)
    parent = _parent_inbound([_panel_certificate(cert_path, key_path)], [8080])
    child = _child_inbound(CHILD_TAG, 8080)
    inbounds = [parent, child] if parent_first else [child, parent]

    cfg = XRayConfig(_config(inbounds))

    certificate = _parent_certificates(cfg)[0]
    assert "certificateFile" not in certificate
    assert "keyFile" not in certificate
    assert certificate["certificate"][0] == "-----BEGIN CERTIFICATE-----"
    assert certificate["key"][0] == "-----BEGIN PRIVATE KEY-----"
    assert cfg._inbounds_by_tag[f"{CHILD_TAG}<=>{PARENT_TAG}"]["sni"] == [SERVER_NAME, SERVER_NAME]
    assert cfg._inbounds_by_tag[PARENT_TAG]["sni"] == [SERVER_NAME, SERVER_NAME]


def test_explicit_fallback_parent_panel_certificate_is_inlined_in_to_str(tmp_path: Path) -> None:
    cert_path, key_path = _write_self_signed(tmp_path)
    parent = _parent_inbound([_panel_certificate(cert_path, key_path)], [8080])
    child = _child_inbound(CHILD_TAG, 8080)

    cfg = XRayConfig(_config([parent, child]), fallbacks_inbound_tags={PARENT_TAG})

    certificate = _emitted_parent(cfg)["streamSettings"]["tlsSettings"]["certificates"][0]
    assert "certificateFile" not in certificate
    assert "keyFile" not in certificate
    assert certificate["certificate"][0] == "-----BEGIN CERTIFICATE-----"
    assert certificate["key"][0] == "-----BEGIN PRIVATE KEY-----"


@pytest.mark.parametrize("parent_first", [True, False])
def test_explicit_fallback_parent_node_certificate_survives_two_children(parent_first: bool) -> None:
    parent = _parent_inbound([_node_served_certificate()], [8080, 8081])
    children = [_child_inbound("vless-ws-a", 8080), _child_inbound("vless-ws-b", 8081)]
    inbounds = [parent, *children] if parent_first else [*children, parent]

    cfg = XRayConfig(_config(inbounds), fallbacks_inbound_tags={PARENT_TAG})

    certificate = _emitted_parent(cfg)["streamSettings"]["tlsSettings"]["certificates"][0]
    assert certificate == {"certificateFile": NODE_CERT_FILE, "keyFile": NODE_KEY_FILE}


def test_auto_detected_fallback_to_str_matches_expected_document(tmp_path: Path) -> None:
    cert_path, key_path = _write_self_signed(tmp_path)
    parent = _parent_inbound([_panel_certificate(cert_path, key_path)], [8080])
    child = _child_inbound(CHILD_TAG, 8080)

    cfg = XRayConfig(_config([parent, child]))

    cert_lines = Path(cert_path).read_text().splitlines()
    key_lines = Path(key_path).read_text().splitlines()
    expected_parent = {
        "tag": PARENT_TAG,
        "protocol": "vless",
        "listen": "0.0.0.0",
        "port": 443,
        "settings": {"clients": [], "decryption": "none", "fallbacks": [{"dest": 8080}]},
        "streamSettings": {
            "network": "tcp",
            "security": "tls",
            "tlsSettings": {
                "serverName": SERVER_NAME,
                "certificates": [{"certificate": cert_lines, "key": key_lines}],
            },
        },
    }
    assert json.loads(cfg.to_str()) == {
        "inbounds": [expected_parent, child],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
    }


@pytest.mark.parametrize("explicit_tags", [None, {PARENT_TAG}])
def test_input_config_is_not_modified_after_build(tmp_path: Path, explicit_tags: set[str] | None) -> None:
    cert_path, key_path = _write_self_signed(tmp_path)
    raw = _config(
        [
            _parent_inbound([_panel_certificate(cert_path, key_path), _node_served_certificate()], [8080]),
            _child_inbound(CHILD_TAG, 8080),
        ]
    )
    snapshot = deepcopy(raw)

    cfg = XRayConfig(raw, fallbacks_inbound_tags=explicit_tags)
    cfg.to_str()

    assert raw == snapshot
