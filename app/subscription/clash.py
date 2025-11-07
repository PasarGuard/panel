from random import choice
from uuid import UUID

import yaml

from app.models.subscription import (
    SubscriptionInboundData,
    TLSConfig,
    GRPCTransportConfig,
    WebSocketTransportConfig,
    TCPTransportConfig,
)
from app.templates import render_template
from app.utils.helpers import yml_uuid_representer
from config import (
    CLASH_SUBSCRIPTION_TEMPLATE,
)

from . import BaseSubscription


class ClashConfiguration(BaseSubscription):
    def __init__(self):
        super().__init__()
        self.data = {
            "proxies": [],
            "proxy-groups": [],
            # Some clients rely on "rules" option and will fail without it.
            "rules": [],
        }

        # Registry for transport config builders
        self.transport_handlers = {
            "http": self._transport_http,
            "h2": self._transport_h2,
            "ws": self._transport_ws,
            "httpupgrade": self._transport_ws,
            "grpc": self._transport_grpc,
            "gun": self._transport_grpc,
            "tcp": self._transport_tcp,
            "raw": self._transport_tcp,
        }

        # Registry for protocol builders
        self.protocol_handlers = {
            "vmess": self._build_vmess,
            "trojan": self._build_trojan,
            "shadowsocks": self._build_shadowsocks,
        }

    def render(self, reverse=False):
        if reverse:
            self.data["proxies"].reverse()

        yaml.add_representer(UUID, yml_uuid_representer)
        return yaml.dump(
            yaml.safe_load(
                render_template(CLASH_SUBSCRIPTION_TEMPLATE, {"conf": self.data, "proxy_remarks": self.proxy_remarks}),
            ),
            sort_keys=False,
            allow_unicode=True,
        )

    def __str__(self) -> str:
        return self.render()

    def __repr__(self) -> str:
        return self.render()

    def _transport_http(self, config: TCPTransportConfig, path: str, random_user_agent: bool = False):
        """Build HTTP transport config"""
        host = config.host if isinstance(config.host, str) else ""
        result = {
            "path": [path] if path else None,
            "Host": host,
            "headers": {},
        }
        if config.request:
            result.update(config.request)

        if random_user_agent:
            result["headers"]["User-Agent"] = choice(self.user_agent_list)

        return self._normalize_and_remove_none_values(result)

    def _transport_ws(
        self, config: WebSocketTransportConfig, path: str, is_httpupgrade: bool = False, random_user_agent: bool = False
    ):
        """Build WebSocket/HTTPUpgrade transport config"""
        host = config.host if isinstance(config.host, str) else ""

        # Parse early data from path
        max_early_data = None
        early_data_header_name = ""
        if "?ed=" in path:
            path, ed_value = path.split("?ed=")
            (max_early_data,) = ed_value.split("/")
            max_early_data = int(max_early_data)
            early_data_header_name = "Sec-WebSocket-Protocol"

        http_headers = config.http_headers or {}
        result = {
            "path": path,
            "headers": {**http_headers, "Host": host} if http_headers else {"Host": host},
            "v2ray-http-upgrade": is_httpupgrade,
            "v2ray-http-upgrade-fast-open": is_httpupgrade,
            "max-early-data": max_early_data if max_early_data and not is_httpupgrade else None,
            "early-data-header-name": early_data_header_name if max_early_data and not is_httpupgrade else None,
        }
        if random_user_agent:
            result["headers"]["User-Agent"] = choice(self.user_agent_list)

        return self._normalize_and_remove_none_values(result)

    def _transport_grpc(self, config: GRPCTransportConfig, path: str):
        """Build gRPC transport config"""
        path = self.get_grpc_gun(path)
        result = {"grpc-service-name": path}
        return self._normalize_and_remove_none_values(result)

    def _transport_h2(self, config: TCPTransportConfig, path: str):
        """Build HTTP/2 transport config"""
        host = config.host if isinstance(config.host, str) else ""
        result = {
            "path": path,
            "host": [host] if host else None,
        }
        return self._normalize_and_remove_none_values(result)

    def _transport_tcp(self, config: TCPTransportConfig, path: str):
        """Build TCP transport config"""
        host = config.host if isinstance(config.host, str) else ""
        http_headers = config.http_headers or {}
        result = {
            "path": [path] if path else None,
            "headers": {**http_headers, "Host": host} if http_headers else {"Host": host},
        }
        return self._normalize_and_remove_none_values(result)

    def _apply_tls(self, node: dict, tls_config: TLSConfig, protocol: str):
        """Apply TLS settings to node"""
        if not tls_config.tls:
            return

        node["tls"] = True
        sni = tls_config.sni if isinstance(tls_config.sni, str) else ""

        if protocol == "trojan":
            node["sni"] = sni
        else:
            node["servername"] = sni

        if tls_config.alpn_list:
            node["alpn"] = tls_config.alpn_list

        if tls_config.allowinsecure:
            node["skip-cert-verify"] = tls_config.allowinsecure

    def _apply_transport(
        self, node: dict, inbound: SubscriptionInboundData, path: str, random_user_agent: bool = False
    ):
        """Apply transport settings using registry"""
        network = inbound.network

        # Normalize network type for clash
        if network in ("http", "h2", "h3"):
            network = "h2"
        elif (
            network in ("tcp", "raw")
            and hasattr(inbound.transport_config, "header_type")
            and inbound.transport_config.header_type == "http"
        ):
            network = "http"

        is_httpupgrade = inbound.network == "httpupgrade"
        if is_httpupgrade:
            network = "ws"

        node["network"] = network

        # Get transport handler
        handler = self.transport_handlers.get(network)
        if not handler:
            node[f"{network}-opts"] = {}
            return

        # Build transport config
        if network == "ws":
            net_opts = handler(inbound.transport_config, path, is_httpupgrade, random_user_agent)
        elif network == "http":
            net_opts = handler(inbound.transport_config, path, random_user_agent)
        else:
            net_opts = handler(inbound.transport_config, path)

        node[f"{network}-opts"] = net_opts

    def _apply_mux(self, node: dict, mux_settings: dict | None):
        """Apply mux settings if present"""
        if not mux_settings or not (clash_mux := mux_settings.get("clash")):
            return
        if not clash_mux.get("enable"):
            return

        clash_mux_config = {
            "enabled": clash_mux.get("enable"),
            "protocol": clash_mux.get("protocol", "smux"),
            "max-connections": clash_mux.get("max_connections"),
            "min-streams": clash_mux.get("min_streams"),
            "max-streams": clash_mux.get("max_streams"),
            "statistic": clash_mux.get("statistic"),
            "only-tcp": clash_mux.get("only_tcp"),
            "padding": clash_mux.get("padding"),
            "brutal-opts": {
                "enabled": True,
                "up": clash_mux["brutal"]["up_mbps"],
                "down": clash_mux["brutal"]["down_mbps"],
            }
            if clash_mux.get("brutal") and clash_mux["brutal"].get("enable")
            else None,
        }
        node["smux"] = self._normalize_and_remove_none_values(clash_mux_config)

    def _build_vmess(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build VMess node"""
        node = {
            "name": remark,
            "type": "vmess",
            "server": address,
            "port": inbound.port,
            "udp": True,
            "uuid": settings["id"],
            "alterId": 0,
            "cipher": "auto",
        }

        self._apply_tls(node, inbound.tls_config, "vmess")
        self._apply_transport(node, inbound, inbound.transport_config.path, inbound.random_user_agent)
        self._apply_mux(node, inbound.mux_settings)

        return node

    def _build_trojan(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build Trojan node"""
        node = {
            "name": remark,
            "type": "trojan",
            "server": address,
            "port": inbound.port,
            "udp": True,
            "password": settings["password"],
        }

        self._apply_tls(node, inbound.tls_config, "trojan")
        self._apply_transport(node, inbound, inbound.transport_config.path, inbound.random_user_agent)
        self._apply_mux(node, inbound.mux_settings)

        return node

    def _build_shadowsocks(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build Shadowsocks node"""
        return {
            "name": remark,
            "type": "ss",
            "server": address,
            "port": inbound.port,
            "network": inbound.network,
            "udp": True,
            "password": settings["password"],
            "cipher": settings["method"],
        }

    def add(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict):
        # not supported by clash
        if inbound.network in ("kcp", "splithttp", "xhttp"):
            return

        proxy_remark = self._remark_validation(remark)

        # Use registry to build node
        handler = self.protocol_handlers.get(inbound.protocol)
        if not handler:
            return

        node = handler(proxy_remark, address, inbound, settings)
        if node:
            self.data["proxies"].append(node)
            self.proxy_remarks.append(proxy_remark)


class ClashMetaConfiguration(ClashConfiguration):
    def __init__(self):
        super().__init__()
        # Override protocol handlers to include vless
        self.protocol_handlers = {
            "vmess": self._build_vmess,
            "vless": self._build_vless,
            "trojan": self._build_trojan,
            "shadowsocks": self._build_shadowsocks_meta,
        }

    def _apply_tls_meta(self, node: dict, tls_config: TLSConfig, protocol: str):
        """Apply TLS settings with Reality support for Clash Meta"""
        if not tls_config.tls:
            return

        # Apply base TLS
        super()._apply_tls(node, tls_config, protocol)

        # Add fingerprint
        if tls_config.fingerprint:
            node["client-fingerprint"] = tls_config.fingerprint

        # Add Reality opts
        if tls_config.tls == "reality" and tls_config.reality_public_key:
            node["reality-opts"] = {
                "public-key": tls_config.reality_public_key,
                "short-id": tls_config.reality_short_id or "",
            }

    def _build_vless(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build VLESS node (Clash Meta only)"""
        node = {
            "name": remark,
            "type": "vless",
            "server": address,
            "port": inbound.port,
            "udp": True,
            "uuid": settings["id"],
            "encryption": "" if inbound.encryption == "none" else inbound.encryption,
        }

        # Only add flow if inbound supports it
        if inbound.flow_enabled and (flow := settings.get("flow", "")):
            node["flow"] = flow

        self._apply_tls_meta(node, inbound.tls_config, "vless")
        self._apply_transport(node, inbound, inbound.transport_config.path, inbound.random_user_agent)
        self._apply_mux(node, inbound.mux_settings)

        return node

    def _build_shadowsocks_meta(
        self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict
    ) -> dict:
        """Build Shadowsocks node with 2022 support"""
        method, password = self.detect_shadowsocks_2022(
            inbound.is_2022,
            inbound.method,
            settings["method"],
            inbound.password,
            settings["password"],
            getattr(inbound, "relay_passwords", None),
        )

        return {
            "name": remark,
            "type": "ss",
            "server": address,
            "port": inbound.port,
            "network": inbound.network,
            "udp": True,
            "method": method,
            "cipher": method,
            "password": password,
        }

    def add(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict):
        # not supported by clash-meta
        if inbound.network in ("kcp", "splithttp", "xhttp"):
            return

        # QUIC with header not supported
        if (
            inbound.network == "quic"
            and hasattr(inbound.transport_config, "header_type")
            and inbound.transport_config.header_type != "none"
        ):
            return

        proxy_remark = self._remark_validation(remark)

        # Use registry to build node
        handler = self.protocol_handlers.get(inbound.protocol)
        if not handler:
            return

        node = handler(proxy_remark, address, inbound, settings)
        if node:
            self.data["proxies"].append(node)
            self.proxy_remarks.append(proxy_remark)
