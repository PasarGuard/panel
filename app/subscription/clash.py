from random import choice
from uuid import UUID

import yaml

from app.models.subscription import (
    GRPCTransportConfig,
    SubscriptionInboundData,
    TCPTransportConfig,
    TLSConfig,
    WebSocketTransportConfig,
    XHTTPTransportConfig,
)
from app.templates import render_template_string
from app.utils.helpers import yml_uuid_representer

from . import BaseSubscription


class ClashConfiguration(BaseSubscription):
    def __init__(
        self,
        clash_template_content: str | None = None,
        user_agent_template_content: str | None = None,
        grpc_user_agent_template_content: str | None = None,
    ):
        super().__init__(
            user_agent_template_content=user_agent_template_content,
            grpc_user_agent_template_content=grpc_user_agent_template_content,
        )
        self.clash_template_content = clash_template_content
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
            "xhttp": self._transport_xhttp,
            "splithttp": self._transport_xhttp,
        }

        # Registry for protocol builders
        self.protocol_handlers = {
            "vmess": self._build_vmess,
            "trojan": self._build_trojan,
            "shadowsocks": self._build_shadowsocks,
            "wireguard": self._build_wireguard,
        }

    def render(self):
        yaml.add_representer(UUID, yml_uuid_representer)
        return yaml.dump(
            yaml.safe_load(
                render_template_string(
                    self.clash_template_content,
                    {"conf": self.data, "proxy_remarks": self.proxy_remarks},
                ),
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

    def _transport_xhttp(self, config: XHTTPTransportConfig, path: str, random_user_agent: bool = False):
        """Build XHTTP transport config for Clash Meta"""
        host = config.host if isinstance(config.host, str) else ""
        http_headers = {k: v for k, v in (config.http_headers or {}).items() if k not in ("Host", "host")}

        result = {
            "path": path or "/",
            "host": host,
            "mode": config.mode or "auto",
            "headers": http_headers if http_headers else None,
            "no-grpc-header": config.no_grpc_header,
            "x-padding-bytes": config.x_padding_bytes,
            "download-settings": config.download_settings,
        }

        if random_user_agent:
            headers = result.get("headers") or {}
            headers["User-Agent"] = choice(self.user_agent_list)
            result["headers"] = headers

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

        # Normalize legacy splithttp -> xhttp
        if network == "splithttp":
            network = "xhttp"

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

    def _build_wireguard(
        self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict
    ) -> dict | None:
        """Build WireGuard node for Clash Premium userspace WireGuard."""
        private_key = settings.get("private_key", "")
        peer_ips = list(settings.get("peer_ips") or [])
        public_key = inbound.wireguard_public_key
        if not private_key or not peer_ips or not public_key:
            return None

        ipv4 = None
        ipv6 = None
        for peer_ip in peer_ips:
            ip = peer_ip.split("/", 1)[0]
            if ":" in ip and not ipv6:
                ipv6 = ip
            elif "." in ip and not ipv4:
                ipv4 = ip

        node = {
            "name": remark,
            "type": "wireguard",
            "server": address,
            "port": self._select_port(inbound.port),
            "ip": ipv4,
            "ipv6": ipv6,
            "private-key": private_key,
            "public-key": public_key,
            "preshared-key": inbound.wireguard_pre_shared_key or None,
            "mtu": inbound.wireguard_mtu,
            "udp": True,
        }

        return self._normalize_and_remove_none_values(node)

    @staticmethod
    def _select_port(port: int | str) -> int:
        """Normalize port values from subscription data."""
        if isinstance(port, str):
            try:
                return int(port)
            except ValueError:
                return 0
        return port

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
    def __init__(
        self,
        clash_template_content: str | None = None,
        user_agent_template_content: str | None = None,
        grpc_user_agent_template_content: str | None = None,
    ):
        super().__init__(
            clash_template_content=clash_template_content,
            user_agent_template_content=user_agent_template_content,
            grpc_user_agent_template_content=grpc_user_agent_template_content,
        )
        # Override protocol handlers to include vless
        self.protocol_handlers = {
            "vmess": self._build_vmess,
            "vless": self._build_vless,
            "trojan": self._build_trojan,
            "shadowsocks": self._build_shadowsocks,
            "hysteria": self._build_hysteria,
            "wireguard": self._build_wireguard,
        }

    def _apply_tls(self, node: dict, tls_config: TLSConfig, protocol: str):
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
                "support-x25519mlkem768": bool(tls_config.mldsa65_verify),
            }

    def _build_vless(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build VLESS node (Clash Meta only)"""
        # Handle vless-route if needed (only affects ID)
        id = settings["id"]
        if inbound.vless_route:
            id = self.vless_route(id, inbound.vless_route)

        node = {
            "name": remark,
            "type": "vless",
            "server": address,
            "port": inbound.port,
            "udp": True,
            "uuid": id,
        }
        if inbound.encryption != "none":
            node["encryption"] = inbound.encryption

        # Only add flow if inbound supports it
        if inbound.flow_enabled and (flow := settings.get("flow", "")):
            node["flow"] = flow

        self._apply_tls(node, inbound.tls_config, "vless")
        self._apply_transport(node, inbound, inbound.transport_config.path, inbound.random_user_agent)
        self._apply_mux(node, inbound.mux_settings)

        return node

    def _build_shadowsocks(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build Shadowsocks node with 2022 support"""
        method, password = self.detect_shadowsocks_2022(
            inbound.is_2022,
            inbound.method,
            settings["method"],
            inbound.password,
            settings["password"],
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

    def _build_hysteria(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build Hysteria node with Clash Meta support"""
        node = {
            "name": remark,
            "type": "hysteria2",
            "server": address,
            "port": inbound.port,
            "password": settings["auth"],
        }

        obfs_password, quic_params = self._get_hysteria_data_from_finalmask(inbound.finalmask)

        node["ports"] = quic_params.get("udpHop", {}).get("ports", "")
        node["hop-interval"] = (
            f"{quic_params.get('udpHop', {}).get('hopInterval', '')}s"
            if quic_params.get("udpHop", {}).get("interval")
            else None
        )

        if obfs_password:
            node["obfs"] = "salamander"
            node["obfs-password"] = obfs_password
        node["down"] = quic_params.get("brutalDown")
        node["up"] = quic_params.get("brutalUp")

        self._apply_tls(node, inbound.tls_config, "hysteria")
        self._apply_mux(node, inbound.mux_settings)

        return self._normalize_and_remove_none_values(node)

    def _build_wireguard(
        self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict
    ) -> dict | None:
        """Build WireGuard node using Clash.Meta's documented fields."""
        private_key = settings.get("private_key", "")
        peer_ips = list(settings.get("peer_ips") or [])
        public_key = inbound.wireguard_public_key
        if not private_key or not peer_ips or not public_key:
            return None

        ipv4 = None
        ipv6 = None
        for peer_ip in peer_ips:
            ip = peer_ip.split("/", 1)[0]
            if ":" in ip and not ipv6:
                ipv6 = ip
            elif "." in ip and not ipv4:
                ipv4 = ip

        node = {
            "name": remark,
            "type": "wireguard",
            "server": address,
            "port": self._select_port(inbound.port),
            "ip": ipv4,
            "ipv6": ipv6,
            "private-key": private_key,
            "public-key": public_key,
            "allowed-ips": inbound.wireguard_allowed_ips or ["0.0.0.0/0", "::/0"],
            "pre-shared-key": inbound.wireguard_pre_shared_key or None,
            "reserved": self._parse_wireguard_reserved(inbound.wireguard_reserved),
            "mtu": inbound.wireguard_mtu,
            "udp": True,
        }

        return self._normalize_and_remove_none_values(node)

    @staticmethod
    def _parse_wireguard_reserved(reserved: str | None) -> list[int] | str | None:
        if not reserved:
            return None

        parts = [part.strip() for part in reserved.split(",")]
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            return [int(part) for part in parts]

        return reserved

    def add(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict):
        # not supported by clash-meta
        if inbound.network in ("kcp"):
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
