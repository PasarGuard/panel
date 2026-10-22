"""Opt-in native PasarGuard node + Xray, not a mocked node endpoint.

CI supplies checksum-pinned binaries. Tests start only ephemeral local services;
no existing or production node is contacted or stopped.
"""

import asyncio
import datetime
import importlib.util
import ipaddress
import json
import os
import socket
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import psutil
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PasarGuardNodeBridge import RestNode
from PasarGuardNodeBridge.common.service_pb2 import BackendType

from app.jobs import node_checker
from config import runtime_settings, server_settings
from role import Role
from scripts.generate_xray_config import build_config


@pytest.mark.skipif(
    not (os.environ.get("NATIVE_NODE_BINARY") and os.environ.get("XRAY_BINARY")),
    reason="Native node/Xray binaries required; real-node CI supplies checksum-pinned assets",
)
@pytest.mark.asyncio
async def test_native_core_stops_before_drain_and_transport_close(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local-node-test")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    cert_path.write_text(cert_pem)
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    key_path.chmod(0o600)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    api_key = str(uuid4())
    env = {
        **os.environ,
        "NODE_HOST": "127.0.0.1",
        "SERVICE_PORT": str(port),
        "SERVICE_PROTOCOL": "rest",
        "SSL_CERT_FILE": str(cert_path),
        "SSL_KEY_FILE": str(key_path),
        "API_KEY": api_key,
        "XRAY_EXECUTABLE_PATH": str(Path(os.environ["XRAY_BINARY"]).resolve()),
        "XRAY_ASSETS_PATH": str(Path(os.environ["XRAY_BINARY"]).resolve().parent),
        "GENERATED_CONFIG_PATH": str(tmp_path / "generated"),
    }
    log = (tmp_path / "node.log").open("wb")
    process = await asyncio.create_subprocess_exec(
        str(Path(os.environ["NATIVE_NODE_BINARY"]).resolve()), cwd=tmp_path, env=env, stdout=log, stderr=log
    )
    node = RestNode("127.0.0.1", port, port, cert_pem, api_key, name="native-shutdown-test")
    probe = RestNode("127.0.0.1", port, port, cert_pem, api_key, name="native-state-probe")
    try:
        async with asyncio.timeout(20):
            while True:
                try:
                    info = await probe.info(timeout=1)
                    assert info.node_version
                    break
                except Exception:
                    if process.returncode is not None:
                        raise RuntimeError((tmp_path / "node.log").read_text()) from None
                    await asyncio.sleep(0.05)
        started = await node.start(json.dumps(build_config(behind_tls_proxy=True)), BackendType.XRAY, [], keep_alive=0)
        assert started.started is True
        assert (await probe.info()).started is True
        xray_children = [
            child for child in psutil.Process(process.pid).children(recursive=True) if child.name() == "xray"
        ]
        assert xray_children, "The native node did not spawn the real Xray executable"
        monkeypatch.setattr(runtime_settings, "role", Role.ALL_IN_ONE)
        monkeypatch.setattr(server_settings, "workers", 1)
        monkeypatch.setattr(node_checker.node_manager, "get_nodes", AsyncMock(return_value={1: node}))
        path = Path(__file__).resolve().parents[1] / "app/lifecycle.py"
        spec = importlib.util.spec_from_file_location("native_test_lifecycle", path)
        lifecycle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lifecycle)
        lifecycle.configure_shutdown(timeout=20, hook_timeout=10)
        events = []
        maintenance = asyncio.create_task(asyncio.Event().wait())
        node_checker._node_loop_tasks.append(maintenance)

        async def stop_loops():
            await node_checker._stop_node_loops()
            assert maintenance.done()
            events.append("quiesced")

        async def stop_nodes():
            await node_checker.shutdown_nodes()
            events.append("native-stop")

        async def drain():
            assert (await probe.info()).started is False
            async with asyncio.timeout(3):
                while any(child.is_running() for child in xray_children):
                    await asyncio.sleep(0.02)
            events.append("drain")

        async def close_transport():
            await probe.stop()
            events.append("close")

        lifecycle.on_shutdown(close_transport, phase=lifecycle.ShutdownPhase.TRANSPORTS)
        lifecycle.on_shutdown(drain, phase=lifecycle.ShutdownPhase.DRAIN)
        lifecycle.on_shutdown(stop_nodes, phase=lifecycle.ShutdownPhase.PRODUCERS)
        lifecycle.on_shutdown(stop_loops, phase=lifecycle.ShutdownPhase.QUIESCE)
        async with lifecycle.lifespan(None):
            pass
        assert events == ["quiesced", "native-stop", "drain", "close"]
    finally:
        await node_checker._stop_node_loops()
        await node.stop()
        await probe.stop()
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except TimeoutError:
                process.kill()
                await process.wait()
        log.close()
