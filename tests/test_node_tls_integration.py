"""Exercise the panel adapter against bridge 0.11 on real local TLS sockets."""

import ssl
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest
from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from grpclib.const import Cardinality, Handler
from grpclib.server import Server
from PasarGuardNodeBridge import NodeAPIError, NodeType
from PasarGuardNodeBridge.common.service_pb2 import BaseInfoResponse, Empty

from app.node.bridge import create_node

API_KEY = "123e4567-e89b-12d3-a456-426614174000"


@asynccontextmanager
async def tls_node(tmp_path, transport, *, identity="127.0.0.1", expired=False):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=-1 if expired else 1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address(identity))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "certificate.pem"
    key_path = tmp_path / "key.pem"
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    cert_path.write_text(pem)
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    ctx.set_alpn_protocols(["h2", "http/1.1"])
    received = []

    async def rest_info(request):
        received.append(("main", request.headers.get("x-api-key")))
        return web.Response(body=BaseInfoResponse(node_version="0.11.0").SerializeToString())

    async def maintenance(request):
        received.append(("maintenance", request.headers.get("x-api-key")))
        return web.json_response({"ok": True})

    class Service:
        async def info(self, stream):
            await stream.recv_message()
            received.append(("main", stream.metadata.get("x-api-key")))
            await stream.send_message(BaseInfoResponse(node_version="0.11.0"))

        def __mapping__(self):
            return {
                "/service.NodeService/GetBaseInfo": Handler(
                    self.info,
                    Cardinality.UNARY_UNARY,
                    Empty,
                    BaseInfoResponse,
                )
            }

    app = web.Application()
    app.router.add_get("/info", rest_info)
    app.router.add_get("/", maintenance)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0, ssl_context=ctx)
    await site.start()
    http_port = site._server.sockets[0].getsockname()[1]
    grpc_server = None
    try:
        main_port = http_port
        if transport == NodeType.grpc:
            grpc_server = Server([Service()])
            await grpc_server.start("127.0.0.1", 0, ssl=ctx)
            main_port = grpc_server._server.sockets[0].getsockname()[1]
        yield (
            {
                "address": "127.0.0.1",
                "port": main_port,
                "api_port": http_port,
                "api_key": API_KEY,
            },
            pem,
            cert.fingerprint(hashes.SHA256()).hex(),
            cert_path,
            received,
        )
    finally:
        if grpc_server is not None:
            grpc_server.close()
            await grpc_server.wait_closed()
        await runner.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", [NodeType.rest, NodeType.grpc])
@pytest.mark.parametrize("policy", ["pin", "both", "pem", "system"])
async def test_tls_policies_allow_main_and_maintenance(tmp_path, monkeypatch, transport, policy):
    async with tls_node(tmp_path, transport) as (kwargs, pem, pin, cert_path, received):
        if policy == "system":
            monkeypatch.setenv("SSL_CERT_FILE", str(cert_path))
        node = create_node(
            transport,
            **kwargs,
            server_ca=pem if policy in ("pem", "both") else "",
            certificate_sha256=pin if policy in ("pin", "both") else None,
        )
        try:
            for _ in range(2):  # Include pooled connection reuse.
                assert (await node.info()).node_version == "0.11.0"
                assert await node.check_connectivity()
            assert received == [("main", API_KEY), ("maintenance", API_KEY)] * 2
            # Reconnect using the same verified policy after closing local pools.
            await node.aclose()
            assert (await node.info()).node_version == "0.11.0"
        finally:
            await node.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", [NodeType.rest, NodeType.grpc])
@pytest.mark.parametrize("failure", ["pin", "identity", "dates", "issuer"])
async def test_tls_failures_withhold_credentials(tmp_path, monkeypatch, transport, failure):
    async with tls_node(
        tmp_path,
        transport,
        identity="127.0.0.2" if failure == "identity" else "127.0.0.1",
        expired=failure == "dates",
    ) as (kwargs, pem, pin, cert_path, received):
        # Even valid PEM and a trusted issuer cannot override a configured wrong pin.
        monkeypatch.setenv("SSL_CERT_FILE", str(cert_path) if failure != "issuer" else str(tmp_path / "missing"))
        node = create_node(
            transport,
            **kwargs,
            server_ca=pem if failure == "pin" else "",
            certificate_sha256="00" * 32 if failure == "pin" else None if failure == "issuer" else pin,
        )
        try:
            with pytest.raises(NodeAPIError):
                await node.info(timeout=2)
            assert not await node.check_connectivity()
            assert received == []
        finally:
            await node.aclose()
