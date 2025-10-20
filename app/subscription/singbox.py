import json
from random import choice

from app.models.subscription import (
    SubscriptionInboundData,
    TLSConfig,
    GRPCTransportConfig,
    WebSocketTransportConfig,
    TCPTransportConfig,
)
from app.templates import render_template
from app.utils.helpers import UUIDEncoder
from config import SINGBOX_SUBSCRIPTION_TEMPLATE

from . import BaseSubscription


class SingBoxConfiguration(BaseSubscription):
    def __init__(self):
        super().__init__()
        self.config = json.loads(render_template(SINGBOX_SUBSCRIPTION_TEMPLATE))

        # Registry for transport handlers
        self.transport_handlers = {
            "http": self._transport_http,
            "ws": self._transport_ws,
            "grpc": self._transport_grpc,
            "gun": self._transport_grpc,
            "httpupgrade": self._transport_httpupgrade,
            "h2": self._transport_http,
            "h3": self._transport_http,
        }

        # Registry for protocol builders
        self.protocol_handlers = {
            "vmess": self._build_vmess,
            "vless": self._build_vless,
            "trojan": self._build_trojan,
            "shadowsocks": self._build_shadowsocks,
        }

    def add_outbound(self, outbound_data):
        self.config["outbounds"].append(outbound_data)

    def render(self, reverse=False):
        urltest_types = ["vmess", "vless", "trojan", "shadowsocks", "hysteria2", "tuic", "http", "ssh"]
        urltest_tags = [outbound["tag"] for outbound in self.config["outbounds"] if outbound["type"] in urltest_types]
        selector_types = ["vmess", "vless", "trojan", "shadowsocks", "hysteria2", "tuic", "http", "ssh", "urltest"]
        selector_tags = [outbound["tag"] for outbound in self.config["outbounds"] if outbound["type"] in selector_types]

        for outbound in self.config["outbounds"]:
            if outbound.get("type") == "urltest":
                outbound["outbounds"] = urltest_tags

        for outbound in self.config["outbounds"]:
            if outbound.get("type") == "selector":
                outbound["outbounds"] = selector_tags

        if reverse:
            self.config["outbounds"].reverse()
        return json.dumps(self.config, indent=4, cls=UUIDEncoder)

    def add(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict):
        """Add outbound using registry pattern"""
        # Not supported by sing-box
        if inbound.network in ("kcp", "splithttp", "xhttp"):
            return
        if inbound.network == "quic" and getattr(inbound.transport_config, "header_type", "none") != "none":
            return

        remark = self._remark_validation(remark)
        self.proxy_remarks.append(remark)

        # Get protocol handler from registry
        handler = self.protocol_handlers.get(inbound.protocol)
        if not handler:
            return

        # Build outbound
        outbound = handler(remark=remark, address=address, inbound=inbound, settings=settings)
        if outbound:
            self.add_outbound(outbound)

    # ========== Transport Handlers ==========

    def _transport_http(self, config: TCPTransportConfig, path: str, network: str) -> dict:
        """Handle HTTP/H2/H3 transport - only gets TCP config"""
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")

        transport = {
            "type": network if network in ("http", "h2", "h3") else "http",
            "idle_timeout": "15s",
            "ping_timeout": "15s",
            "path": path,
            "host": [host] if host else None,
        }

        if config.header_type == "http" and config.request:
            transport.update(config.request)
        else:
            transport["headers"] = {k: [v] for k, v in config.http_headers.items()} if config.http_headers else {}

        if config.random_user_agent:
            transport.setdefault("headers", {})["User-Agent"] = choice(self.user_agent_list)

        return self._normalize_and_remove_none_values(transport)

    def _transport_ws(self, config: WebSocketTransportConfig, path: str) -> dict:
        """Handle WebSocket transport - only gets WS config"""
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")

        # Parse early data from path
        max_early_data = None
        early_data_header_name = None
        if "?ed=" in path:
            path, ed_part = path.split("?ed=")
            max_early_data = int(ed_part.split("/")[0])
            early_data_header_name = "Sec-WebSocket-Protocol"

        transport = {
            "type": "ws",
            "headers": {k: [v] for k, v in config.http_headers.items()} if config.http_headers else {},
            "path": path,
            "max_early_data": max_early_data,
            "early_data_header_name": early_data_header_name,
        }
        transport["headers"]["host"] = [host] if host else None

        if config.random_user_agent:
            transport["headers"]["User-Agent"] = [choice(self.user_agent_list)]

        return self._normalize_and_remove_none_values(transport)

    def _transport_grpc(self, config: GRPCTransportConfig, path: str) -> dict:
        """Handle GRPC transport - only gets GRPC config"""
        return self._normalize_and_remove_none_values(
            {
                "type": "grpc",
                "service_name": path,
                "idle_timeout": f"{config.idle_timeout}s" if config.idle_timeout else "15s",
                "ping_timeout": f"{config.health_check_timeout}s" if config.health_check_timeout else "15s",
                "permit_without_stream": config.permit_without_stream,
            }
        )

    def _transport_httpupgrade(self, config: WebSocketTransportConfig, path: str) -> dict:
        """Handle HTTPUpgrade transport - only gets WS config (similar to WS)"""
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")

        transport = {
            "type": "httpupgrade",
            "headers": {k: [v] for k, v in config.http_headers.items()} if config.http_headers else {},
            "host": host,
            "path": path,
        }

        if config.random_user_agent:
            transport["headers"]["User-Agent"] = choice(self.user_agent_list)

        return self._normalize_and_remove_none_values(transport)

    def _apply_transport(self, network: str, inbound: SubscriptionInboundData, path: str) -> dict | None:
        """Apply transport settings using registry pattern"""
        # Map network types
        if network in ("tcp", "raw") and getattr(inbound.transport_config, "header_type", "none") == "http":
            network = "http"

        handler = self.transport_handlers.get(network)
        if not handler:
            return None

        # Pass only the config this transport needs
        if network in ("http", "h2", "h3"):
            return handler(inbound.transport_config, path, network)
        else:
            return handler(inbound.transport_config, path)

    def _apply_tls(self, tls_config: TLSConfig, fragment_settings: dict | None = None) -> dict:
        """Apply TLS settings - receives TLS config and optional fragment settings"""
        config = {
            "enabled": tls_config.tls in ("tls", "reality"),
            "server_name": tls_config.sni
            if isinstance(tls_config.sni, str)
            else (tls_config.sni[0] if tls_config.sni else None),
            "insecure": tls_config.allowinsecure,
            "utls": {"enabled": bool(tls_config.fingerprint), "fingerprint": tls_config.fingerprint}
            if tls_config.fingerprint
            else None,
            "alpn": tls_config.alpn_singbox,  # Pre-formatted for sing-box!
            "ech": {
                "enabled": True,
                "config": [],
                "config_path": "",
            }
            if tls_config.ech_config_list
            else None,
            "reality": {
                "enabled": tls_config.tls == "reality",
                "public_key": tls_config.reality_public_key,
                "short_id": tls_config.reality_short_id,
            }
            if tls_config.tls == "reality"
            else None,
        }

        # Fragment settings (from inbound, not TLS) - sing-box embeds in TLS config
        if fragment_settings and (singbox_fragment := fragment_settings.get("sing_box")):
            config.update(singbox_fragment)

        return self._normalize_and_remove_none_values(config)

    # ========== Protocol Builders ==========

    def _build_vmess(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build VMess outbound"""
        return self._build_outbound(
            protocol_type="vmess",
            remark=remark,
            address=address,
            inbound=inbound,
            user_settings={"uuid": str(settings["id"]), "alterId": 0},
        )

    def _build_vless(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build VLESS outbound"""
        return self._build_outbound(
            protocol_type="vless",
            remark=remark,
            address=address,
            inbound=inbound,
            user_settings={"uuid": str(settings["id"]), "flow": settings.get("flow", "")},
        )

    def _build_trojan(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build Trojan outbound"""
        return self._build_outbound(
            protocol_type="trojan",
            remark=remark,
            address=address,
            inbound=inbound,
            user_settings={"password": settings["password"], "flow": settings.get("flow", "")},
        )

    def _build_shadowsocks(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build Shadowsocks outbound"""
        method, password = self.detect_shadowsocks_2022(
            inbound.is_2022,
            inbound.method,
            settings["method"],
            getattr(inbound, "password", None),
            settings["password"],
        )

        config = {
            "type": "shadowsocks",
            "tag": remark,
            "server": address,
            "server_port": self._select_port(inbound.port),
            "method": method,
            "password": password,
        }

        return self._normalize_and_remove_none_values(config)

    def _build_outbound(
        self,
        protocol_type: str,
        remark: str,
        address: str,
        inbound: SubscriptionInboundData,
        user_settings: dict,
    ) -> dict:
        """Generic outbound builder"""
        network = inbound.network
        path = inbound.transport_config.path

        # Process GRPC path
        if network in ("grpc", "gun"):
            path = self.get_grpc_gun(path)

        # Map network aliases
        if network == "h2":
            network = "http"
            # Override ALPN for h2
            inbound.tls_config.alpn_list = ["h2"]
        elif network == "h3":
            network = "http"
            inbound.tls_config.alpn_list = ["h3"]

        config = {
            "type": protocol_type,
            "tag": remark,
            "server": address,
            "server_port": self._select_port(inbound.port),
            **user_settings,
        }

        # Add flow for specific combinations
        header_type = getattr(inbound.transport_config, "header_type", "none")
        if (
            network in ("tcp", "raw", "kcp")
            and header_type != "http"
            and inbound.tls_config.tls in ("tls", "reality")
            and user_settings.get("flow")
        ):
            config["flow"] = user_settings["flow"]

        # Add transport
        if network in ("http", "ws", "quic", "grpc", "httpupgrade", "h2", "h3"):
            transport = self._apply_transport(network, inbound, path)
            if transport:
                config["transport"] = transport

        # Add TLS
        if inbound.tls_config.tls in ("tls", "reality"):
            config["tls"] = self._apply_tls(inbound.tls_config, inbound.fragment_settings)

        # Add mux
        if inbound.mux_settings and (singbox_mux := inbound.mux_settings.get("sing_box")):
            singbox_mux = self._normalize_and_remove_none_values(singbox_mux)
            config["multiplex"] = singbox_mux

        return self._normalize_and_remove_none_values(config)

    def _select_port(self, port: int | str) -> int:
        """Select a random port if multiple are provided"""
        if isinstance(port, str):
            ports = port.split(",")
            return int(choice(ports))
        return port
