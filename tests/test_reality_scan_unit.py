import datetime
import os
import struct

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.utils import reality_scan as rs
from app.utils.reality_scan import RealityScanError


@pytest.mark.parametrize(
    "target,expected",
    [
        ("www.microsoft.com:443", ("www.microsoft.com", 443, "www.microsoft.com")),
        ("cloudflare.com", ("cloudflare.com", 443, "cloudflare.com")),
        ("https://example.com/some/path", ("example.com", 443, "example.com")),
        ("example.com:8443", ("example.com", 8443, "example.com")),
        ("[2606:4700::1111]:443", ("2606:4700::1111", 443, None)),
        ("1.1.1.1:8443", ("1.1.1.1", 8443, None)),
    ],
)
def test_parse_target_ok(target, expected):
    assert rs.parse_target(target) == expected


@pytest.mark.parametrize("bad", ["", "   ", "host:0", "host:70000", "host:abc"])
def test_parse_target_invalid(bad):
    with pytest.raises(RealityScanError):
        rs.parse_target(bad)


@pytest.mark.parametrize("bad", ["a\r\nX-Smuggled: 1", "host\nfoo", "h\x00st", "a\tb"])
def test_parse_target_rejects_control_chars(bad):
    with pytest.raises(RealityScanError):
        rs.parse_target(bad)


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "10.0.0.1", "192.168.1.1", "169.254.169.254", "0.0.0.0", "::1", "fd00::1", "224.0.0.1"],
)
def test_resolve_public_ip_blocks_internal_literals(ip):
    with pytest.raises(RealityScanError):
        rs.resolve_public_ip(ip)


@pytest.mark.parametrize("ip", ["1.1.1.1", "8.8.8.8", "2606:4700:4700::1111"])
def test_resolve_public_ip_allows_public_literals(ip):
    assert rs.resolve_public_ip(ip) == ip


def test_resolve_public_ip_blocks_private_dns(monkeypatch):
    monkeypatch.setattr(
        rs.socket,
        "getaddrinfo",
        lambda *a, **k: [(rs.socket.AF_INET, rs.socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))],
    )
    with pytest.raises(RealityScanError):
        rs.resolve_public_ip("internal.example")


def test_resolve_public_ip_prefers_public_and_ipv4(monkeypatch):
    monkeypatch.setattr(
        rs.socket,
        "getaddrinfo",
        lambda *a, **k: [
            (rs.socket.AF_INET6, rs.socket.SOCK_STREAM, 6, "", ("fd00::5", 0, 0, 0)),
            (rs.socket.AF_INET, rs.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
        ],
    )
    assert rs.resolve_public_ip("example.com") == "93.184.216.34"


def test_build_client_hello_is_well_formed():
    record = rs._build_client_hello("example.com")
    assert record[0] == 0x16
    assert record[1:3] == b"\x03\x01"
    rec_len = (record[3] << 8) | record[4]
    assert rec_len == len(record) - 5
    handshake = record[5:]
    assert handshake[0] == 0x01
    hs_len = (handshake[1] << 16) | (handshake[2] << 8) | handshake[3]
    assert hs_len == len(handshake) - 4


def _server_hello(selected_group: int, *, hrr: bool = False, tls13: bool = True) -> bytes:
    random = rs._HELLO_RETRY_REQUEST_RANDOM if hrr else bytes(32)
    exts = b""
    if tls13:
        sv = struct.pack(">H", 0x0304)
        exts += struct.pack(">HH", 0x002B, len(sv)) + sv
    if hrr:
        ks = struct.pack(">H", selected_group)
    else:
        key = bytes(32)
        ks = struct.pack(">H", selected_group) + struct.pack(">H", len(key)) + key
    exts += struct.pack(">HH", 0x0033, len(ks)) + ks

    session_id = bytes(0)
    body = (
        struct.pack(">H", 0x0303)
        + random
        + bytes([len(session_id)])
        + session_id
        + struct.pack(">H", 0x1301)
        + bytes([0x00])
        + struct.pack(">H", len(exts))
        + exts
    )
    return bytes([0x02]) + len(body).to_bytes(3, "big") + body


def test_parse_server_hello_x25519():
    is_hrr, group, tls13 = rs._parse_server_hello(_server_hello(rs.GROUP_X25519))
    assert (is_hrr, group, tls13) == (False, rs.GROUP_X25519, True)


def test_parse_server_hello_post_quantum_hrr():
    is_hrr, group, tls13 = rs._parse_server_hello(_server_hello(rs.GROUP_X25519MLKEM768, hrr=True))
    assert is_hrr is True
    assert group == rs.GROUP_X25519MLKEM768


def test_group_probe_interpretation(monkeypatch):
    monkeypatch.setattr(rs.socket, "create_connection", lambda *a, **k: _FakeSock(_server_hello(rs.GROUP_X25519)))
    out = rs._group_probe("1.2.3.4", 443, "example.com", 2)
    assert out == {"x25519": True, "post_quantum": False, "curve": "X25519"}

    monkeypatch.setattr(
        rs.socket, "create_connection", lambda *a, **k: _FakeSock(_server_hello(rs.GROUP_X25519MLKEM768, hrr=True))
    )
    out = rs._group_probe("1.2.3.4", 443, "example.com", 2)
    assert out == {"x25519": True, "post_quantum": True, "curve": "X25519MLKEM768"}


def test_group_probe_failure_is_unknown(monkeypatch):
    def boom(*a, **k):
        raise OSError("refused")

    monkeypatch.setattr(rs.socket, "create_connection", boom)
    assert rs._group_probe("1.2.3.4", 443, "example.com", 2) == {"x25519": None, "post_quantum": None, "curve": None}


class _FakeSock:
    def __init__(self, server_hello: bytes):
        record = bytes([0x16]) + struct.pack(">H", 0x0303) + struct.pack(">H", len(server_hello)) + server_hello
        self._buf = record

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def settimeout(self, _):
        pass

    def sendall(self, _):
        pass

    def recv(self, n):
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk


def _self_signed_der(cn: str, sans: list[str]) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Org")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(s) for s in sans]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.DER)


def test_parse_certificate_extracts_sans_and_filters_wildcards():
    der = _self_signed_der("example.com", ["example.com", "*.example.com", "www.example.com"])
    out = rs._parse_certificate(der)
    assert out["cert_subject"] == "example.com"
    assert out["cert_issuer"] == "Test Org"
    assert out["server_names"] == ["example.com", "www.example.com"]
    assert out["not_after"] is not None


def test_parse_certificate_handles_none():
    assert rs._parse_certificate(None)["server_names"] == []


def test_first_usable_name_prefers_common_name():
    der = _self_signed_der("cloudflare-dns.com", ["cloudflare-dns.com", "one.one.one.one"])
    assert rs._first_usable_name(der) == "cloudflare-dns.com"


def test_first_usable_name_skips_wildcard_cn_uses_san():
    der = _self_signed_der("*.example.com", ["*.example.com", "www.example.com"])
    assert rs._first_usable_name(der) == "www.example.com"


def test_first_usable_name_none_when_all_wildcard():
    der = _self_signed_der("*.example.com", ["*.example.com"])
    assert rs._first_usable_name(der) is None


def test_first_usable_name_none_when_no_cert():
    assert rs._first_usable_name(None) is None


def _patch_probes(monkeypatch, *, tls, group, h3):
    monkeypatch.setattr(rs, "_tls_probe", lambda *a, **k: tls)
    monkeypatch.setattr(rs, "_group_probe", lambda *a, **k: group)
    monkeypatch.setattr(rs, "_h3_probe", lambda *a, **k: h3)


_GOOD_TLS = {
    "tls13": True,
    "tls_version": "1.3",
    "alpn": "h2",
    "h2": True,
    "cert_valid": True,
    "cert_subject": "example.com",
    "cert_issuer": "CA",
    "not_after": "2030-01-01T00:00:00+00:00",
    "server_names": ["example.com"],
    "latency_ms": 42,
    "reason": None,
    "sni": "example.com",
    "sni_discovered": False,
}


def test_scan_sync_feasible_when_all_pass(monkeypatch):
    _patch_probes(monkeypatch, tls=dict(_GOOD_TLS), group={"x25519": True, "post_quantum": True, "curve": "X25519MLKEM768"}, h3=True)
    out = rs._scan_sync("example.com", "93.184.216.34", 443, "example.com", 5)
    assert out["feasible"] is True
    assert out["post_quantum"] is True
    assert out["h3"] is True


def test_scan_sync_feasible_when_group_unknown(monkeypatch):
    _patch_probes(monkeypatch, tls=dict(_GOOD_TLS), group={"x25519": None, "post_quantum": None, "curve": None}, h3=False)
    out = rs._scan_sync("example.com", "93.184.216.34", 443, "example.com", 5)
    assert out["feasible"] is True


def test_scan_sync_carries_discovered_sni(monkeypatch):
    tls = dict(_GOOD_TLS, sni="cloudflare-dns.com", sni_discovered=True)
    _patch_probes(monkeypatch, tls=tls, group={"x25519": True, "post_quantum": True, "curve": "X25519MLKEM768"}, h3=False)
    out = rs._scan_sync("1.0.0.1", "1.0.0.1", 443, None, 5)
    assert out["sni"] == "cloudflare-dns.com"
    assert out["sni_discovered"] is True
    assert out["feasible"] is True


def test_scan_sync_not_feasible_when_definitely_not_x25519(monkeypatch):
    _patch_probes(monkeypatch, tls=dict(_GOOD_TLS), group={"x25519": False, "post_quantum": False, "curve": "secp256r1"}, h3=False)
    out = rs._scan_sync("example.com", "93.184.216.34", 443, "example.com", 5)
    assert out["feasible"] is False


def test_scan_sync_not_feasible_without_tls13(monkeypatch):
    tls = dict(_GOOD_TLS, tls13=False, tls_version="1.2")
    _patch_probes(monkeypatch, tls=tls, group={"x25519": True, "post_quantum": False, "curve": "X25519"}, h3=False)
    out = rs._scan_sync("example.com", "93.184.216.34", 443, "example.com", 5)
    assert out["feasible"] is False


def test_scan_sync_skips_extra_probes_when_unreachable(monkeypatch):
    tls = dict(_GOOD_TLS, tls13=False, tls_version=None, h2=False, cert_valid=False, reason="Connection timed out.")
    called = {"group": False, "h3": False}

    def group(*a, **k):
        called["group"] = True
        return {"x25519": None, "post_quantum": None, "curve": None}

    def h3(*a, **k):
        called["h3"] = True
        return False

    monkeypatch.setattr(rs, "_tls_probe", lambda *a, **k: tls)
    monkeypatch.setattr(rs, "_group_probe", group)
    monkeypatch.setattr(rs, "_h3_probe", h3)
    out = rs._scan_sync("example.com", "93.184.216.34", 443, "example.com", 5)
    assert out["feasible"] is False
    assert called == {"group": False, "h3": False}


@pytest.mark.skipif(os.environ.get("REALITY_SCAN_NETWORK_TEST") != "1", reason="network test opt-in")
@pytest.mark.asyncio
async def test_scan_reality_target_live_example():
    result = await rs.scan_reality_target("example.com:443", timeout=8)
    assert result["tls13"] is True
    assert result["h2"] is True
    assert result["cert_valid"] is True
    assert result["latency_ms"] is not None
    assert result["sni"] == "example.com"
    assert result["sni_discovered"] is False


@pytest.mark.skipif(os.environ.get("REALITY_SCAN_NETWORK_TEST") != "1", reason="network test opt-in")
@pytest.mark.asyncio
async def test_scan_reality_target_bare_ip_discovers_sni():
    result = await rs.scan_reality_target("1.0.0.1:443", timeout=8)
    assert result["sni_discovered"] is True
    assert result["sni"]
    assert result["cert_valid"] is True


def _frame(payload: bytes, rtype: int = 0x16) -> bytes:
    return bytes([rtype]) + struct.pack(">H", 0x0303) + struct.pack(">H", len(payload)) + payload


class _RawSock:
    def __init__(self, raw: bytes):
        self._buf = raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def settimeout(self, _):
        pass

    def sendall(self, _):
        pass

    def recv(self, n):
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk


def test_select_public_ip_prefers_public_v4_over_private_v6():
    infos = [
        (rs.socket.AF_INET6, rs.socket.SOCK_STREAM, 6, "", ("fd00::1", 0, 0, 0)),
        (rs.socket.AF_INET, rs.socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0)),
    ]
    assert rs._select_public_ip("h", infos) == "1.2.3.4"


def test_select_public_ip_all_private_raises():
    infos = [(rs.socket.AF_INET, rs.socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0))]
    with pytest.raises(RealityScanError):
        rs._select_public_ip("h", infos)


@pytest.mark.asyncio
async def test_resolve_public_ip_async_times_out(monkeypatch):
    import asyncio

    async def slow(*a, **k):
        await asyncio.sleep(30)

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", slow)
    with pytest.raises(RealityScanError, match="timed out"):
        await rs._resolve_public_ip_async("slow.example", 0.2)


@pytest.mark.asyncio
async def test_resolve_public_ip_async_literal_skips_dns():
    assert await rs._resolve_public_ip_async("1.1.1.1", 1.0) == "1.1.1.1"


def test_read_first_handshake_message_reassembles_across_records():
    sh = _server_hello(rs.GROUP_X25519)
    split = len(sh) // 2
    raw = _frame(sh[:split]) + _frame(sh[split:])
    msg = rs._read_first_handshake_message(_RawSock(raw), deadline=__import__("time").monotonic() + 5)
    assert msg == sh


def test_read_first_handshake_message_alert_returns_none():
    raw = _frame(b"\x02\x28", rtype=0x15)
    msg = rs._read_first_handshake_message(_RawSock(raw), deadline=__import__("time").monotonic() + 5)
    assert msg is None


def test_group_probe_non_x25519_group(monkeypatch):
    monkeypatch.setattr(rs.socket, "create_connection", lambda *a, **k: _FakeSock(_server_hello(0x0017)))
    out = rs._group_probe("1.2.3.4", 443, "example.com", 2)
    assert out == {"x25519": False, "post_quantum": False, "curve": "secp256r1"}


def test_parse_certificate_without_sans():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "no-san.example")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=90))
        .sign(key, hashes.SHA256())
    )
    out = rs._parse_certificate(cert.public_bytes(serialization.Encoding.DER))
    assert out["cert_subject"] == "no-san.example"
    assert out["server_names"] == []


def test_scan_sync_not_feasible_without_h2(monkeypatch):
    tls = dict(_GOOD_TLS, h2=False, alpn="http/1.1")
    _patch_probes(monkeypatch, tls=tls, group={"x25519": True, "post_quantum": True, "curve": "X25519MLKEM768"}, h3=False)
    out = rs._scan_sync("example.com", "93.184.216.34", 443, "example.com", 5)
    assert out["feasible"] is False


@pytest.mark.asyncio
async def test_scan_concurrency_is_capped(monkeypatch):
    import asyncio
    import threading
    import time as _time

    rs._scan_semaphore = None
    lock = threading.Lock()
    state = {"live": 0, "peak": 0}
    resolver = {"live": 0, "peak": 0}

    async def fake_resolve(host, timeout):
        resolver["live"] += 1
        resolver["peak"] = max(resolver["peak"], resolver["live"])
        await asyncio.sleep(0.02)
        resolver["live"] -= 1
        return "93.184.216.34"

    def fake_sync(*a, **k):
        with lock:
            state["live"] += 1
            state["peak"] = max(state["peak"], state["live"])
        _time.sleep(0.05)
        with lock:
            state["live"] -= 1
        return {"feasible": False}

    monkeypatch.setattr(rs, "_resolve_public_ip_async", fake_resolve)
    monkeypatch.setattr(rs, "_scan_sync", fake_sync)

    await asyncio.gather(*[rs.scan_reality_target("example.com:443") for _ in range(12)])
    assert state["peak"] <= rs.MAX_CONCURRENT_SCANS
    assert resolver["peak"] <= rs.MAX_CONCURRENT_SCANS
