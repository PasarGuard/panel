"""Read vmess, vless, trojan and shadowsocks share links as the host data the subscription builders take."""

import base64
import json
from urllib.parse import parse_qsl, unquote, urlsplit

from app.models.subscription import (
    GRPCTransportConfig,
    KCPTransportConfig,
    SubscriptionInboundData,
    TCPTransportConfig,
    TLSConfig,
    WebSocketTransportConfig,
    XHTTPTransportConfig,
)

# What a malformed link raises from parse_share_link or a builder (pydantic's ValidationError is a ValueError).
SHARE_LINK_ERRORS = (ValueError, KeyError, TypeError, AttributeError, IndexError)

# Share link transports with a JSON counterpart; the link names its transport like the host does.
_SHARE_LINK_TRANSPORTS = {
    "tcp": TCPTransportConfig,
    "raw": TCPTransportConfig,
    "h2": TCPTransportConfig,
    "ws": WebSocketTransportConfig,
    "httpupgrade": WebSocketTransportConfig,
    "grpc": GRPCTransportConfig,
    "gun": GRPCTransportConfig,
    "xhttp": XHTTPTransportConfig,
    "splithttp": XHTTPTransportConfig,
    "kcp": KCPTransportConfig,
}


def _b64decode_text(value: str) -> str:
    """Decode standard or URL-safe base64, with or without padding."""
    value = value.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(value + "=" * (-len(value) % 4), validate=True).decode()


def parse_share_link(link: str) -> tuple[str, SubscriptionInboundData, dict, dict | None] | None:
    """Read a vmess, vless, trojan or shadowsocks share link as the host data the JSON builder takes.

    Return ``(remark, inbound, settings, xhttp_extra)``, or None for another scheme or transport.
    A malformed link raises ``ValueError`` (pydantic's ``ValidationError`` included), ``KeyError``,
    ``TypeError`` or ``AttributeError``.
    """
    scheme, _, rest = link.partition("://")
    scheme = scheme.lower()
    if scheme == "vmess":
        data = json.loads(_b64decode_text(rest))
        params = {key: str(value) for key, value in data.items() if value is not None}
        network = params.get("net") or "tcp"
        header_type = params.get("type", "")
        # VMess links keep the TLS mode in "tls" and the header type, gRPC or xHTTP mode in "type".
        params.update(type=network, security=params.get("tls") or "none")
        if network in ("grpc", "gun"):
            # The link builder percent-encodes a gRPC path, like the query of the other schemes.
            params.update(
                mode=header_type, serviceName=unquote(params.get("path", "")), authority=params.get("host", "")
            )
        elif network in ("xhttp", "splithttp"):
            params["mode"] = header_type
        else:
            params["headerType"] = header_type
        protocol, address, port = "vmess", params["add"], int(params["port"])
        remark, settings = params.get("ps", ""), {"id": params["id"]}
    elif scheme in ("vless", "trojan", "ss"):
        # Split by hand: standard base64 credentials may hold "/", which ends a URL authority.
        body, _, fragment = rest.partition("#")
        head, _, query = body.partition("?")
        if scheme == "ss" and "@" not in head:
            # Legacy form: the whole "method:password@host:port" is base64.
            head = _b64decode_text(unquote(head))
        userinfo, at, server = head.rpartition("@")
        server = urlsplit(f"//{server}")
        if not at or not server.hostname or server.port is None:
            raise ValueError("share link without credentials, address or port")
        protocol, address, port = {"ss": "shadowsocks"}.get(scheme, scheme), server.hostname, server.port
        params, remark = dict(parse_qsl(query)), unquote(fragment)
        if scheme == "ss":
            # SIP002: base64 of "method:password", or "method:password" percent-encoded (2022 methods).
            if ":" in userinfo:
                method, _, password = (unquote(part) for part in userinfo.partition(":"))
            else:
                method, _, password = _b64decode_text(unquote(userinfo)).partition(":")
            settings = {"method": method, "password": password}
        else:
            settings = {"id" if scheme == "vless" else "password": unquote(userinfo)}
    else:
        return None

    network = params.get("type") or "tcp"
    security = params.get("security") or "none"
    transport_class = _SHARE_LINK_TRANSPORTS.get(network)
    if transport_class is None or security not in ("none", "tls", "reality"):
        return None
    if protocol == "shadowsocks" and transport_class is not TCPTransportConfig:
        # The Shadowsocks builder has no transport; another one would be dropped silently.
        return None

    if transport_class is GRPCTransportConfig:
        transport = GRPCTransportConfig(
            path=params.get("serviceName", ""),
            host=params.get("authority", ""),
            multi_mode=params.get("mode") == "multi",
        )
    elif transport_class is XHTTPTransportConfig:
        transport = XHTTPTransportConfig(
            path=params.get("path", ""), host=params.get("host", ""), mode=params.get("mode") or "auto"
        )
    elif transport_class is TCPTransportConfig:
        transport = TCPTransportConfig(
            path=params.get("path", ""), host=params.get("host", ""), header_type=params.get("headerType") or "none"
        )
    elif transport_class is KCPTransportConfig:
        transport = KCPTransportConfig()
    else:
        transport = transport_class(path=params.get("path", ""), host=params.get("host", ""))

    inbound = SubscriptionInboundData(
        remark=remark,
        inbound_tag="",
        protocol=protocol,
        address=address,
        port=port,
        network=network,
        tls_config=TLSConfig(
            # A host without TLS keeps None; Clash reads any value as TLS on.
            tls=None if security == "none" else security,
            sni=params.get("sni", ""),
            fingerprint=params.get("fp", ""),
            allowinsecure=params.get("allowInsecure", params.get("insecure", "")).lower() in ("1", "true"),
            alpn_list=[alpn for alpn in params.get("alpn", "").split(",") if alpn],
            ech_config_list=params.get("ech") or None,
            pinned_peer_cert_sha256=params.get("pcs") or None,
            reality_public_key=params.get("pbk", ""),
            reality_short_id=params.get("sid", ""),
            reality_spx=params.get("spx", ""),
            mldsa65_verify=params.get("pqv") or None,
        ),
        transport_config=transport,
        encryption=params.get("encryption") or "none",
        inbound_flow=params.get("flow", ""),
    )
    xhttp_extra = None
    if transport_class is XHTTPTransportConfig and params.get("extra"):
        xhttp_extra = json.loads(params["extra"])
        if not isinstance(xhttp_extra, dict):
            raise ValueError("xHTTP extra is not a JSON object")
    return remark or address, inbound, settings, xhttp_extra
