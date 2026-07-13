import asyncio
import ipaddress
import os
import socket
import ssl
import struct
import time

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import x25519 as _x25519
from cryptography.x509.oid import ExtensionOID, NameOID

from app.utils.logger import get_logger

logger = get_logger("reality-scan")

DEFAULT_PORT = 443
DEFAULT_TIMEOUT = 10.0
MIN_TIMEOUT = 1.0
MAX_TIMEOUT = 20.0
DNS_TIMEOUT = 5.0
MAX_CONCURRENT_SCANS = 4

_scan_semaphore: "asyncio.Semaphore | None" = None


def _get_scan_semaphore() -> "asyncio.Semaphore":
    global _scan_semaphore
    if _scan_semaphore is None:
        _scan_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCANS)
    return _scan_semaphore

GROUP_X25519 = 0x001D
GROUP_X25519MLKEM768 = 0x11EC
GROUP_X25519KYBER768DRAFT00 = 0x6399
GROUP_NAMES: dict[int, str] = {
    0x0017: "secp256r1",
    0x0018: "secp384r1",
    0x0019: "secp521r1",
    0x001D: "X25519",
    0x001E: "x448",
    0x11EC: "X25519MLKEM768",
    0x6399: "X25519Kyber768Draft00",
}
_POST_QUANTUM_GROUPS = {GROUP_X25519MLKEM768, GROUP_X25519KYBER768DRAFT00}
_X25519_GROUPS = {GROUP_X25519, GROUP_X25519MLKEM768}

_HELLO_RETRY_REQUEST_RANDOM = bytes.fromhex("cf21ad74e59a6111be1d8c021e65b891c2a211167abb8c5e079e09e2c8a8339c")


class RealityScanError(ValueError):
    pass


def parse_target(target: str, sni_override: str | None = None) -> tuple[str, int, str | None]:
    if not target or not target.strip():
        raise RealityScanError("A target host is required.")

    value = target.strip()
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.split("/", 1)[0].strip()
    if not value:
        raise RealityScanError("A target host is required.")

    if value.startswith("["):
        close = value.find("]")
        if close == -1:
            raise RealityScanError("Invalid IPv6 target: missing closing bracket.")
        host = value[1:close]
        rest = value[close + 1 :]
        port = _parse_port(rest[1:]) if rest.startswith(":") else DEFAULT_PORT
    elif value.count(":") == 1:
        host, port_str = value.rsplit(":", 1)
        port = _parse_port(port_str)
    else:
        host = value
        port = DEFAULT_PORT

    host = host.strip()
    if not host:
        raise RealityScanError("A target host is required.")

    sni: str | None
    if sni_override and sni_override.strip():
        sni = sni_override.strip()
    else:
        sni = None if _is_ip_literal(host) else host

    return host, port, sni


def _parse_port(port_str: str) -> int:
    port_str = port_str.strip()
    if not port_str:
        return DEFAULT_PORT
    try:
        port = int(port_str)
    except ValueError:
        raise RealityScanError(f"Invalid port: {port_str!r}")
    if not (1 <= port <= 65535):
        raise RealityScanError("Port must be between 1 and 65535.")
    return port


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _address_is_public(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(ip_obj.is_global) and not (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def _select_public_ip(host: str, infos: list) -> str:
    candidates = sorted(infos, key=lambda info: 0 if info[0] == socket.AF_INET else 1)
    saw_blocked = False
    for _family, _type, _proto, _canon, sockaddr in candidates:
        ip = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if _address_is_public(ip_obj):
            return ip
        saw_blocked = True

    if saw_blocked:
        raise RealityScanError("Target resolves only to private or reserved addresses; only public hosts can be scanned.")
    raise RealityScanError(f"Could not resolve host to a usable address: {host}")


def resolve_public_ip(host: str) -> str:
    if _is_ip_literal(host):
        ip_obj = ipaddress.ip_address(host)
        if not _address_is_public(ip_obj):
            raise RealityScanError("Target address is private or reserved; only public hosts can be scanned.")
        return host

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise RealityScanError(f"Could not resolve host: {host}")
    return _select_public_ip(host, infos)


async def _resolve_public_ip_async(host: str, timeout: float) -> str:
    if _is_ip_literal(host):
        return resolve_public_ip(host)

    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(loop.getaddrinfo(host, None, type=socket.SOCK_STREAM), timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError):
        raise RealityScanError(f"DNS lookup for {host} timed out.")
    except socket.gaierror:
        raise RealityScanError(f"Could not resolve host: {host}")
    return _select_public_ip(host, infos)


def _clamp_timeout(timeout: float | None) -> float:
    if not timeout or timeout <= 0:
        return DEFAULT_TIMEOUT
    return max(MIN_TIMEOUT, min(MAX_TIMEOUT, float(timeout)))


def _name_common_name(name: x509.Name) -> str | None:
    try:
        attrs = name.get_attributes_for_oid(NameOID.COMMON_NAME)
        if attrs:
            return str(attrs[0].value)
    except Exception:
        pass
    return None


def _name_organization(name: x509.Name) -> str | None:
    try:
        attrs = name.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
        if attrs:
            return str(attrs[0].value)
    except Exception:
        pass
    return None


def _parse_certificate(der: bytes | None) -> dict:
    out: dict = {"cert_subject": None, "cert_issuer": None, "not_after": None, "server_names": []}
    if not der:
        return out
    try:
        cert = x509.load_der_x509_certificate(der)
    except Exception as exc:
        logger.debug("reality-scan: failed to parse certificate: %s", exc)
        return out

    out["cert_subject"] = _name_common_name(cert.subject) or (cert.subject.rfc4514_string() or None)
    out["cert_issuer"] = _name_organization(cert.issuer) or _name_common_name(cert.issuer) or (cert.issuer.rfc4514_string() or None)

    try:
        out["not_after"] = cert.not_valid_after_utc.isoformat()
    except Exception:
        try:
            out["not_after"] = cert.not_valid_after.isoformat()
        except Exception:
            out["not_after"] = None

    try:
        san = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        dns_names = san.value.get_values_for_type(x509.DNSName)
        seen: set[str] = set()
        server_names: list[str] = []
        for name in dns_names:
            if name.startswith("*.") or name in seen:
                continue
            seen.add(name)
            server_names.append(name)
        out["server_names"] = server_names
    except x509.ExtensionNotFound:
        pass
    except Exception as exc:
        logger.debug("reality-scan: failed to read SANs: %s", exc)

    return out


def _tls_probe(ip: str, port: int, sni: str | None, timeout: float) -> dict:
    result: dict = {
        "tls13": False,
        "tls_version": None,
        "alpn": None,
        "h2": False,
        "cert_valid": False,
        "cert_subject": None,
        "cert_issuer": None,
        "not_after": None,
        "server_names": [],
        "latency_ms": None,
        "reason": None,
    }

    verify_ctx = ssl.create_default_context()
    verify_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    verify_ctx.set_alpn_protocols(["h2", "http/1.1"])
    if sni is None:
        verify_ctx.check_hostname = False
        verify_ctx.verify_mode = ssl.CERT_NONE

    permissive_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    permissive_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    permissive_ctx.check_hostname = False
    permissive_ctx.verify_mode = ssl.CERT_NONE
    permissive_ctx.set_alpn_protocols(["h2", "http/1.1"])

    der: bytes | None = None
    version: str | None = None
    alpn: str | None = None

    def _handshake(ctx: ssl.SSLContext) -> tuple[str | None, str | None, bytes | None, float]:
        started = time.monotonic()
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=sni) as tls:
                latency = (time.monotonic() - started) * 1000.0
                return tls.version(), tls.selected_alpn_protocol(), tls.getpeercert(binary_form=True), latency

    try:
        version, alpn, der, latency = _handshake(verify_ctx)
        result["cert_valid"] = sni is not None
        result["latency_ms"] = round(latency)
    except ssl.SSLCertVerificationError as exc:
        result["reason"] = f"Certificate did not validate: {getattr(exc, 'verify_message', None) or exc}"
        try:
            version, alpn, der, latency = _handshake(permissive_ctx)
            result["latency_ms"] = round(latency)
        except Exception as exc2:
            result["reason"] = f"TLS handshake failed: {exc2}"
            return result
    except (socket.timeout, TimeoutError):
        result["reason"] = "Connection timed out."
        return result
    except ssl.SSLError as exc:
        result["reason"] = f"TLS handshake failed: {exc}"
        return result
    except (ConnectionRefusedError, ConnectionResetError, OSError) as exc:
        result["reason"] = f"Connection failed: {exc}"
        return result

    result["tls_version"] = _pretty_tls_version(version)
    result["tls13"] = version == "TLSv1.3"
    result["alpn"] = alpn
    result["h2"] = alpn == "h2"
    result.update(_parse_certificate(der))
    return result


def _pretty_tls_version(version: str | None) -> str | None:
    if not version:
        return None
    mapping = {"TLSv1.3": "1.3", "TLSv1.2": "1.2", "TLSv1.1": "1.1", "TLSv1": "1.0"}
    return mapping.get(version, version)


def _build_client_hello(sni: str | None) -> bytes:
    priv = _x25519.X25519PrivateKey.generate()
    x25519_pub = priv.public_key().public_bytes_raw()

    extensions = b""

    if sni:
        try:
            sni_bytes = sni.encode("idna")
        except Exception:
            try:
                sni_bytes = sni.encode("ascii")
            except Exception:
                sni_bytes = b""
        if sni_bytes:
            host_entry = b"\x00" + struct.pack(">H", len(sni_bytes)) + sni_bytes
            sni_list = struct.pack(">H", len(host_entry)) + host_entry
            extensions += struct.pack(">HH", 0x0000, len(sni_list)) + sni_list

    sv = bytes([0x02]) + struct.pack(">H", 0x0304)
    extensions += struct.pack(">HH", 0x002B, len(sv)) + sv

    groups = struct.pack(">HHHHH", GROUP_X25519MLKEM768, GROUP_X25519, 0x0017, 0x001E, 0x0018)
    sg = struct.pack(">H", len(groups)) + groups
    extensions += struct.pack(">HH", 0x000A, len(sg)) + sg

    ks_entry = struct.pack(">HH", GROUP_X25519, len(x25519_pub)) + x25519_pub
    client_shares = struct.pack(">H", len(ks_entry)) + ks_entry
    extensions += struct.pack(">HH", 0x0033, len(client_shares)) + client_shares

    algs = struct.pack(">HHHHHHHH", 0x0403, 0x0804, 0x0401, 0x0503, 0x0805, 0x0501, 0x0806, 0x0601)
    sa = struct.pack(">H", len(algs)) + algs
    extensions += struct.pack(">HH", 0x000D, len(sa)) + sa

    pkem = bytes([0x01, 0x01])
    extensions += struct.pack(">HH", 0x002D, len(pkem)) + pkem

    alpn_protos = bytes([len(b"h2")]) + b"h2" + bytes([len(b"http/1.1")]) + b"http/1.1"
    alpn = struct.pack(">H", len(alpn_protos)) + alpn_protos
    extensions += struct.pack(">HH", 0x0010, len(alpn)) + alpn

    ext_block = struct.pack(">H", len(extensions)) + extensions

    client_random = os.urandom(32)
    session_id = os.urandom(32)
    cipher_suites = struct.pack(">HHH", 0x1301, 0x1302, 0x1303)
    body = (
        struct.pack(">H", 0x0303)
        + client_random
        + bytes([len(session_id)])
        + session_id
        + struct.pack(">H", len(cipher_suites))
        + cipher_suites
        + bytes([0x01, 0x00])
        + ext_block
    )

    handshake = bytes([0x01]) + len(body).to_bytes(3, "big") + body
    record = bytes([0x16]) + struct.pack(">H", 0x0301) + struct.pack(">H", len(handshake)) + handshake
    return record


def _recv_exact(sock: socket.socket, count: int, deadline: float) -> bytes | None:
    buf = b""
    while len(buf) < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        sock.settimeout(remaining)
        try:
            chunk = sock.recv(count - len(buf))
        except (socket.timeout, TimeoutError):
            return None
        if not chunk:
            return None
        buf += chunk
    return buf


def _read_first_handshake_message(sock: socket.socket, deadline: float) -> bytes | None:
    hs_buf = b""
    for _ in range(16):
        header = _recv_exact(sock, 5, deadline)
        if not header or len(header) < 5:
            return None
        rtype = header[0]
        rlen = (header[3] << 8) | header[4]
        if rlen == 0:
            continue
        payload = _recv_exact(sock, rlen, deadline)
        if payload is None:
            return None
        if rtype == 0x15:
            return None
        if rtype == 0x16:
            hs_buf += payload
            if len(hs_buf) >= 4:
                msg_len = (hs_buf[1] << 16) | (hs_buf[2] << 8) | hs_buf[3]
                if len(hs_buf) >= 4 + msg_len:
                    return hs_buf[: 4 + msg_len]
    return None


def _parse_server_hello(msg: bytes) -> tuple[bool, int | None, bool]:
    if len(msg) < 4 or msg[0] != 0x02:
        return False, None, False
    body = msg[4:]
    if len(body) < 35:
        return False, None, False

    server_random = body[2:34]
    is_hrr = server_random == _HELLO_RETRY_REQUEST_RANDOM

    idx = 34
    if idx >= len(body):
        return is_hrr, None, False
    sid_len = body[idx]
    idx += 1 + sid_len
    idx += 2
    idx += 1
    if idx + 2 > len(body):
        return is_hrr, None, False
    ext_total = (body[idx] << 8) | body[idx + 1]
    idx += 2
    end = min(idx + ext_total, len(body))

    selected_group: int | None = None
    is_tls13 = False
    while idx + 4 <= end:
        etype = (body[idx] << 8) | body[idx + 1]
        elen = (body[idx + 2] << 8) | body[idx + 3]
        edata = body[idx + 4 : idx + 4 + elen]
        if etype == 0x002B and len(edata) >= 2:
            if ((edata[0] << 8) | edata[1]) == 0x0304:
                is_tls13 = True
        elif etype == 0x0033 and len(edata) >= 2:
            selected_group = (edata[0] << 8) | edata[1]
        idx += 4 + elen

    return is_hrr, selected_group, is_tls13


def _group_probe(ip: str, port: int, sni: str | None, timeout: float) -> dict:
    result = {"x25519": None, "post_quantum": None, "curve": None}
    try:
        deadline = time.monotonic() + timeout
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.sendall(_build_client_hello(sni))
            msg = _read_first_handshake_message(sock, deadline)
        if not msg:
            return result
        _is_hrr, selected_group, _is_tls13 = _parse_server_hello(msg)
        if selected_group is None:
            return result
        result["curve"] = GROUP_NAMES.get(selected_group, f"0x{selected_group:04x}")
        result["post_quantum"] = selected_group in _POST_QUANTUM_GROUPS
        result["x25519"] = selected_group in _X25519_GROUPS
        return result
    except Exception as exc:
        logger.debug("reality-scan: group probe failed for %s:%s: %s", ip, port, exc)
        return result


def _h3_probe(host: str, ip: str, port: int, sni: str | None, timeout: float) -> bool:
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.set_alpn_protocols(["http/1.1"])
        request_host = sni or host
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=sni) as tls:
                tls.settimeout(timeout)
                request = (
                    f"GET / HTTP/1.1\r\nHost: {request_host}\r\n"
                    "User-Agent: PasarGuard-RealityScan/1.0\r\nAccept: */*\r\nConnection: close\r\n\r\n"
                )
                tls.sendall(request.encode("ascii", "ignore"))
                data = b""
                while len(data) < 32768:
                    chunk = tls.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\r\n\r\n" in data:
                        break
        header_blob = data.split(b"\r\n\r\n", 1)[0].decode("latin-1", "ignore")
        for line in header_blob.split("\r\n"):
            lower = line.lower()
            if lower.startswith("alt-svc:") and "h3" in lower:
                return True
        return False
    except Exception as exc:
        logger.debug("reality-scan: h3 probe failed for %s:%s: %s", ip, port, exc)
        return False


def _scan_sync(host: str, ip: str, port: int, sni: str | None, timeout: float) -> dict:
    tls = _tls_probe(ip, port, sni, timeout)

    result: dict = {
        "target": f"{host}:{port}",
        "host": host,
        "ip": ip,
        "port": port,
        "sni": sni,
        "feasible": False,
        "tls13": tls["tls13"],
        "tls_version": tls["tls_version"],
        "h2": tls["h2"],
        "alpn": tls["alpn"],
        "x25519": None,
        "post_quantum": None,
        "curve": None,
        "h3": False,
        "cert_valid": tls["cert_valid"],
        "cert_subject": tls["cert_subject"],
        "cert_issuer": tls["cert_issuer"],
        "not_after": tls["not_after"],
        "server_names": tls["server_names"],
        "latency_ms": tls["latency_ms"],
        "reason": tls["reason"],
    }

    if tls["tls_version"] is None:
        return result

    group = _group_probe(ip, port, sni, timeout)
    result["x25519"] = group["x25519"]
    result["post_quantum"] = group["post_quantum"]
    result["curve"] = group["curve"]
    result["h3"] = _h3_probe(host, ip, port, sni, timeout)

    definitely_not_x25519 = group["x25519"] is False and group["post_quantum"] is False and group["curve"] is not None
    result["feasible"] = bool(result["tls13"] and result["h2"] and result["cert_valid"] and not definitely_not_x25519)
    return result


async def scan_reality_target(target: str, sni: str | None = None, timeout: float | None = None) -> dict:
    host, port, resolved_sni = parse_target(target, sni)
    clamped = _clamp_timeout(timeout)
    async with _get_scan_semaphore():
        ip = await _resolve_public_ip_async(host, min(clamped, DNS_TIMEOUT))
        return await asyncio.to_thread(_scan_sync, host, ip, port, resolved_sni, clamped)
