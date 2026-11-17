import asyncio
import hashlib
import os
import ssl
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models.certificate import CertificateFingerprintRequest
from app.routers.authentication import get_current
from app.routers.core import router
from app.utils import certificate as certificate_utils
from app.utils.certificate import CertificateFingerprintError, get_certificate_fingerprint


@pytest.fixture
def certificate_files(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "node.example.test")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem = certificate.public_bytes(serialization.Encoding.PEM)
    der = certificate.public_bytes(serialization.Encoding.DER)
    cert_path = tmp_path / "certificate.pem"
    der_path = tmp_path / "certificate.der"
    key_path = tmp_path / "private.key"
    cert_path.write_bytes(pem)
    der_path.write_bytes(der)
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return SimpleNamespace(
        pem=pem.decode(),
        der=der,
        cert_path=cert_path,
        der_path=der_path,
        key_path=key_path,
        sha256=hashlib.sha256(der).hexdigest(),
    )


@pytest.mark.parametrize("source", ["pem", "file_path", "der_file"])
@pytest.mark.asyncio
async def test_hashes_complete_certificate_der(certificate_files, source):
    cert = certificate_files
    data = (
        {"pem": cert.pem}
        if source == "pem"
        else {"file_path": str(cert.der_path if source == "der_file" else cert.cert_path)}
    )
    assert await get_certificate_fingerprint(CertificateFingerprintRequest(**data)) == cert.sha256


@pytest.mark.asyncio
async def test_uses_first_pem_certificate(certificate_files):
    # A different (also valid) certificate follows the leaf in this chain.
    other_key = ec.generate_private_key(ec.SECP256R1())
    leaf = x509.load_pem_x509_certificate(certificate_files.pem.encode())
    other = (
        x509.CertificateBuilder()
        .subject_name(leaf.subject)
        .issuer_name(leaf.issuer)
        .public_key(other_key.public_key())
        .serial_number(2)
        .not_valid_before(leaf.not_valid_before_utc)
        .not_valid_after(leaf.not_valid_after_utc)
        .sign(other_key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
        .decode()
    )
    result = await get_certificate_fingerprint(CertificateFingerprintRequest(pem=certificate_files.pem + other))
    assert result == certificate_files.sha256


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"pem": "x", "server": "localhost"},
        {"file_path": "x", "server": "localhost"},
        {"pem": ""},
        {"server": "https://example.com"},
        {"server": "host:443"},
        {"server": "host\nname"},
        {"server": "localhost", "port": 0},
        {"server": "localhost", "port": 65536},
        {"server": "localhost", "timeout": 21},
        {"server": "localhost", "timeout": float("nan")},
        {"pem": "x", "timeout": 10},
    ],
)
def test_validates_source_and_probe_settings(data):
    with pytest.raises(ValidationError):
        CertificateFingerprintRequest(**data)


@pytest.mark.parametrize("host", ["127.0.0.1", "10.0.0.1", "::1", "node.example.test", "localhost"])
def test_accepts_node_hosts_including_private_addresses(host):
    assert CertificateFingerprintRequest(server=host).server == host


@pytest.mark.asyncio
async def test_rejects_invalid_pem_and_files(tmp_path):
    invalid = tmp_path / "invalid.pem"
    invalid.write_text("not a certificate")
    oversized = tmp_path / "oversized.pem"
    oversized.write_bytes(b"x" * (certificate_utils.MAX_CERTIFICATE_BYTES + 1))
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    for data in [
        {"pem": "not a certificate"},
        {"file_path": str(invalid)},
        {"file_path": str(tmp_path / "missing")},
        {"file_path": str(tmp_path)},
        {"file_path": str(oversized)},
        {"file_path": str(fifo)},
    ]:
        with pytest.raises(CertificateFingerprintError):
            await asyncio.wait_for(get_certificate_fingerprint(CertificateFingerprintRequest(**data)), timeout=2)


@pytest.mark.asyncio
async def test_fetches_live_self_signed_tls_certificate_with_sni(certificate_files):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate_files.cert_path, certificate_files.key_path)
    received_names = []
    context.set_servername_callback(lambda _socket, name, _context: received_names.append(name))

    def handle_connection(_reader, writer):
        writer.close()

    server = await asyncio.start_server(handle_connection, "127.0.0.1", 0, ssl=context)
    async with server:
        port = server.sockets[0].getsockname()[1]
        result = await get_certificate_fingerprint(
            CertificateFingerprintRequest(server="127.0.0.1", port=port, server_name="node.example.test")
        )
    assert result == certificate_files.sha256
    assert received_names == ["node.example.test"]


@pytest.mark.asyncio
async def test_live_probe_times_out(monkeypatch):
    async def stalled_connection(*args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(certificate_utils.asyncio, "open_connection", stalled_connection)
    with pytest.raises(CertificateFingerprintError, match="timed out") as error:
        await get_certificate_fingerprint(CertificateFingerprintRequest(server="localhost", timeout=1))
    assert error.value.status_code == 504


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current] = lambda: SimpleNamespace(is_owner=True)
    with TestClient(app) as client:
        yield client


def test_endpoint_hashes_pem_and_file(api_client, certificate_files):
    for payload in [{"pem": certificate_files.pem}, {"file_path": str(certificate_files.cert_path)}]:
        response = api_client.post("/api/core/certificate-fingerprint", json=payload)
        assert response.status_code == 200
        assert response.json() == {"sha256": certificate_files.sha256}


def test_endpoint_validation_and_invalid_certificate(api_client):
    assert api_client.post("/api/core/certificate-fingerprint", json={}).status_code == 422
    response = api_client.post("/api/core/certificate-fingerprint", json={"pem": "invalid"})
    assert response.status_code == 400
    assert "Invalid certificate" in response.json()["detail"]


@pytest.mark.parametrize("status_code", [502, 504])
def test_endpoint_maps_probe_errors(api_client, monkeypatch, status_code):
    async def failed_probe(request):
        raise CertificateFingerprintError("probe failed", status_code)

    monkeypatch.setattr(certificate_utils, "_server_certificate", failed_probe)
    response = api_client.post("/api/core/certificate-fingerprint", json={"server": "localhost"})
    assert response.status_code == status_code
    assert response.json() == {"detail": "probe failed"}


def test_endpoint_requires_core_read_permission(api_client):
    api_client.app.dependency_overrides[get_current] = lambda: SimpleNamespace(
        is_owner=False, is_limited=False, role=None
    )
    response = api_client.post("/api/core/certificate-fingerprint", json={"server": "localhost"})
    assert response.status_code == 403


def test_endpoint_requires_authentication(api_client):
    api_client.app.dependency_overrides.clear()
    response = api_client.post("/api/core/certificate-fingerprint", json={"server": "localhost"})
    assert response.status_code == 401
