"""Real local TLS handshakes; NOT replacements for external reachability probes."""

import asyncio
import contextlib
import datetime
import ssl

import pytest
import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.utils import reality_scan


@pytest_asyncio.fixture(loop_scope="function")
async def tls_endpoint(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "probe.example.test")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("probe.example.test")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    key_path.chmod(0o600)
    monkeypatch.setenv("SSL_CERT_FILE", str(cert_path))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.set_alpn_protocols(["h2", "http/1.1"])
    context.load_cert_chain(cert_path, key_path)
    tasks = set()

    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            await reader.read(1)
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
            tasks.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=context, ssl_handshake_timeout=2)
    try:
        yield server.sockets[0].getsockname()[1]
    finally:
        server.close()
        await server.wait_closed()
        if tasks:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=3)


@pytest.mark.asyncio
@pytest.mark.parametrize("sni", ["probe.example.test", None])
async def test_real_tls13_h2_certificate_and_sni_discovery(tls_endpoint, sni):
    # Call the TLS layer directly: production SSRF guards still reject loopback.
    result = await asyncio.to_thread(reality_scan._tls_probe, "127.0.0.1", tls_endpoint, sni, 2)
    assert result["tls13"] is True, result.get("reason")
    assert result["h2"] is True, result
    assert result["cert_valid"] is True, result
    assert result["sni"] == "probe.example.test"
    assert result["sni_discovered"] is (sni is None)
    assert result["latency_ms"] is not None
