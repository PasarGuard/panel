import base64
import json
import urllib.parse as urlparse
from random import choice
from urllib.parse import quote

from app.models.subscription import (
    GRPCTransportConfig,
    KCPTransportConfig,
    QUICTransportConfig,
    SubscriptionInboundData,
    TCPTransportConfig,
    TLSConfig,
    WebSocketTransportConfig,
    XHTTPTransportConfig,
)
from config import EXTERNAL_CONFIG

from . import BaseSubscription


class StandardLinks(BaseSubscription):
    def __init__(self):
        super().__init__()
        self.links = []

        # Registry pattern for transport handlers
        self.transport_handlers = {
            "grpc": self._transport_grpc,
            "gun": self._transport_grpc,
            "splithttp": self._transport_xhttp,
            "xhttp": self._transport_xhttp,
            "ws": self._transport_ws,
            "httpupgrade": self._transport_httpupgrade,
            "quic": self._transport_quic,
            "kcp": self._transport_kcp,
            "tcp": self._transport_tcp,
            "raw": self._transport_tcp,
            "http": self._transport_tcp,
            "h2": self._transport_tcp,
        }

        # Registry pattern for protocol handlers
        self.protocol_handlers = {
            "vmess": self._build_vmess,
            "vless": self._build_vless,
            "trojan": self._build_trojan,
            "shadowsocks": self._build_shadowsocks,
        }

    def add_link(self, link):
        self.links.append(link)

    def render(self, reverse=False):
        if EXTERNAL_CONFIG:
            self.links.append(EXTERNAL_CONFIG)
        if reverse:
            self.links.reverse()
        return "\n".join((self.links))

    def add(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict):
        """
        Add a proxy link using registry pattern.
        No if/else chains - just lookup the handler and call it.
        """
        # Get protocol handler from registry
        handler = self.protocol_handlers.get(inbound.protocol)
        if not handler:
            return

        # Call the handler
        link = handler(remark=remark, address=address, inbound=inbound, settings=settings)
        if link:
            self.add_link(link)

    # ========== Transport Handlers (Only receive what they need) ==========

    def _transport_grpc(self, payload: dict, protocol: str, config: GRPCTransportConfig, path: str):
        """Handle grpc/gun transport - only gets GRPC config"""
        host = config.host if isinstance(config.host, str) else ""

        if protocol == "vmess":
            payload["type"] = "multi" if config.multi_mode else "gun"
        else:
            payload["serviceName"] = path
            payload["authority"] = host
            payload["mode"] = "multi" if config.multi_mode else "gun"

    def _transport_xhttp(self, payload: dict, protocol: str, config: XHTTPTransportConfig, path: str):
        """Handle splithttp/xhttp transport - only gets xHTTP config"""
        host = config.host if isinstance(config.host, str) else ""
        payload["path"] = path
        payload["host"] = host

        if protocol == "vmess":
            payload["type"] = config.mode
        else:
            payload["mode"] = config.mode

        extra = {
            "scMaxEachPostBytes": config.sc_max_each_post_bytes,
            "scMinPostsIntervalMs": config.sc_min_posts_interval_ms,
            "xPaddingBytes": config.x_padding_bytes,
            "xPaddingObfsMode": config.x_padding_obfs_mode,
            "xPaddingKey": config.x_padding_key,
            "xPaddingHeader": config.x_padding_header,
            "xPaddingPlacement": config.x_padding_placement,
            "xPaddingMethod": config.x_padding_method,
            "uplinkHTTPMethod": config.uplink_http_method,
            "sessionPlacement": config.session_placement,
            "sessionKey": config.session_key,
            "seqPlacement": config.seq_placement,
            "seqKey": config.seq_key,
            "uplinkDataPlacement": config.uplink_data_placement,
            "uplinkDataKey": config.uplink_data_key,
            "uplinkChunkSize": config.uplink_chunk_size,
            "noGRPCHeader": config.no_grpc_header,
            "xmux": config.xmux,
            "headers": config.http_headers if config.http_headers else {},
            "downloadSettings": config.download_settings,
        }

        if config.random_user_agent:
            if config.mode in ("stream-one", "stream-up") and not config.no_grpc_header:
                extra["headers"]["User-Agent"] = choice(self.grpc_user_agent_data)
            else:
                extra["headers"]["User-Agent"] = choice(self.user_agent_list)

        extra = self._normalize_and_remove_none_values(extra)
        if extra:
            payload["extra"] = json.dumps(extra).replace(" ", "")

    def _transport_ws(self, payload: dict, protocol: str, config: WebSocketTransportConfig, path: str):
        """Handle websocket transport - only gets WS config"""
        host = config.host if isinstance(config.host, str) else ""
        if config.heartbeat_period:
            payload["heartbeatPeriod"] = config.heartbeat_period
        payload["path"] = path
        payload["host"] = host

    def _transport_httpupgrade(self, payload: dict, protocol: str, config: WebSocketTransportConfig, path: str):
        """Handle httpupgrade transport - only gets HTTPUPGRADE config"""
        host = config.host if isinstance(config.host, str) else ""
        payload["path"] = path
        payload["host"] = host

    def _transport_quic(self, payload: dict, protocol: str, config: QUICTransportConfig, path: str):
        """Handle quic transport - only gets QUIC config"""
        if protocol != "vmess":
            host = config.host if isinstance(config.host, str) else ""
            payload["key"] = path
            payload["quicSecurity"] = host

    def _transport_kcp(self, payload: dict, protocol: str, config: KCPTransportConfig, path: str):
        """Handle kcp transport - only gets KCP config"""
        # KCP header/seed are removed in latest Xray-core; no extra fields needed.

    def _transport_tcp(self, payload: dict, protocol: str, config: TCPTransportConfig, path: str):
        """Handle tcp/raw/http transport - only gets TCP config"""
        host = config.host if isinstance(config.host, str) else ""
        payload["path"] = path
        payload["host"] = host

    def _apply_transport_settings(self, payload: dict, protocol: str, inbound: SubscriptionInboundData, path: str):
        """Apply transport settings - uses pre-created config instance"""
        handler = self.transport_handlers.get(inbound.network)
        if handler:
            # Just use the stored instance, no extraction needed!
            handler(payload, protocol, inbound.transport_config, path)

    def _apply_tls_settings(self, payload: dict, tls_config: TLSConfig, fragment_settings: dict | None = None):
        """Apply TLS settings - receives TLS config and optional fragment settings"""
        sni = tls_config.sni if isinstance(tls_config.sni, str) else ""
        payload["sni"] = sni
        payload["fp"] = tls_config.fingerprint
        payload["pcs"] = tls_config.pinned_peer_cert_sha256
        payload["vcn"] = ",".join(tls_config.verify_peer_cert_by_name) if tls_config.verify_peer_cert_by_name else ""

        # Use pre-formatted alpn for links (comma-separated string)
        if tls_config.alpn_links:
            payload["alpn"] = tls_config.alpn_links

        # Fragment settings (from inbound, not TLS)
        if fragment_settings:
            if xray_fragment := fragment_settings.get("xray"):
                payload["fragment"] = (
                    f"{xray_fragment['length']},{xray_fragment['interval']},{xray_fragment['packets']}"
                )

        if tls_config.ech_config_list:
            payload["echConfigList"] = tls_config.ech_config_list

        if tls_config.tls == "reality":
            payload["pbk"] = tls_config.reality_public_key
            payload["sid"] = tls_config.reality_short_id
            if tls_config.reality_spx:
                payload["spx"] = tls_config.reality_spx
            if tls_config.mldsa65_verify:
                payload["pqv"] = tls_config.mldsa65_verify

        if tls_config.allowinsecure:
            payload["allowInsecure"] = 1

    # ========== Protocol Builders ==========

    def _build_vmess(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> str:
        """Build VMess link"""
        # Process grpc path
        path = self._process_path(inbound)
        host = inbound.transport_config.host if isinstance(inbound.transport_config.host, str) else ""

        payload = {
            "add": address,
            "aid": "0",
            "host": host,
            "id": str(settings["id"]),
            "net": inbound.network,
            "path": path,
            "port": inbound.port,
            "ps": remark,
            "scy": "auto",
            "tls": inbound.tls_config.tls,
            "type": getattr(inbound.transport_config, "header_type", "none"),
            "v": "2",
        }

        self._apply_transport_settings(payload, "vmess", inbound, path)

        if inbound.tls_config.tls in ("tls", "reality"):
            # Use stored TLS config instance
            self._apply_tls_settings(payload, inbound.tls_config, inbound.fragment_settings)

        payload = self._normalize_and_remove_none_values(payload)
        return "vmess://" + base64.b64encode(json.dumps(payload, sort_keys=True).encode("utf-8")).decode()

    def _build_vless(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> str:
        """Build VLESS link"""
        # Process grpc path
        path = self._process_path(inbound)

        # Handle vless-route if needed (only affects ID)
        id = settings["id"]
        if inbound.vless_route:
            id = self.vless_route(id, inbound.vless_route)

        payload = {
            "encryption": inbound.encryption,
            "security": inbound.tls_config.tls,
            "type": inbound.network,
            "headerType": getattr(inbound.transport_config, "header_type", "none"),
        }

        # Only add flow if inbound supports it
        if inbound.flow_enabled and (flow := settings.get("flow", "")):
            payload["flow"] = flow

        self._apply_transport_settings(payload, "vless", inbound, path)

        if inbound.tls_config.tls in ("tls", "reality"):
            # Use stored TLS config instance
            self._apply_tls_settings(payload, inbound.tls_config, inbound.fragment_settings)

        payload = self._normalize_and_remove_none_values(payload)
        return f"vless://{id}@{address}:{inbound.port}?{urlparse.urlencode(payload)}#{urlparse.quote(remark)}"

    def _build_trojan(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> str:
        """Build Trojan link"""
        # Process grpc path
        path = self._process_path(inbound)

        payload = {
            "security": inbound.tls_config.tls,
            "type": inbound.network,
            "headerType": getattr(inbound.transport_config, "header_type", "none"),
        }

        self._apply_transport_settings(payload, "trojan", inbound, path)

        if inbound.tls_config.tls in ("tls", "reality"):
            # Use stored TLS config instance
            self._apply_tls_settings(payload, inbound.tls_config, inbound.fragment_settings)

        payload = self._normalize_and_remove_none_values(payload)
        password = urlparse.quote(settings["password"], safe=":")
        return f"trojan://{password}@{address}:{inbound.port}?{urlparse.urlencode(payload)}#{urlparse.quote(remark)}"

    def _build_shadowsocks(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> str:
        """Build Shadowsocks link"""
        method, password = self.detect_shadowsocks_2022(
            inbound.is_2022,
            inbound.method,
            settings["method"],
            getattr(inbound, "password", None),
            settings["password"],
        )

        encoded = base64.b64encode(f"{method}:{password}".encode()).decode()
        return f"ss://{encoded}@{address}:{inbound.port}#{urlparse.quote(remark)}"

    # ========== Helper Methods ==========

    def _process_path(self, inbound: SubscriptionInboundData) -> str:
        """Process path for grpc if needed"""
        path = inbound.transport_config.path
        if inbound.network in ("grpc", "gun"):
            multi_mode = getattr(inbound.transport_config, "multi_mode", False)
            if multi_mode:
                path = self.get_grpc_multi(path)
            else:
                path = self.get_grpc_gun(path)
            if inbound.transport_config.path.startswith("/"):
                path = quote(path, safe="-_.!~*'()")
        return path
