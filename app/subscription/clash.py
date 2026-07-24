from random import choice
from uuid import UUID

import yaml
from pydantic import BaseModel

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

        http_headers = dict(config.http_headers or {})
        if host:
            http_headers = {k: v for k, v in http_headers.items() if k not in ("Host", "host")}
            http_headers["Host"] = host

        result = {
            "path": path,
            "headers": http_headers,
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
        host = self._select_host(config.host)
        http_headers = {k: v for k, v in (config.http_headers or {}).items() if k not in ("Host", "host")}

        result = {
            "path": path or "/",
            "host": host,
            "mode": config.mode or "auto",
            "headers": http_headers if http_headers else None,
            "no-grpc-header": config.no_grpc_header,
            "x-padding-bytes": config.x_padding_bytes,
            "x-padding-obfs-mode": config.x_padding_obfs_mode,
            "x-padding-key": config.x_padding_key,
            "x-padding-header": config.x_padding_header,
            "x-padding-placement": config.x_padding_placement,
            "x-padding-method": config.x_padding_method,
            "uplink-http-method": config.uplink_http_method,
            "session-placement": config.session_placement,
            "session-key": config.session_key,
            "seq-placement": config.seq_placement,
            "seq-key": config.seq_key,
            "uplink-data-placement": config.uplink_data_placement,
            "uplink-data-key": config.uplink_data_key,
            "uplink-chunk-size": config.uplink_chunk_size,
            "sc-max-each-post-bytes": config.sc_max_each_post_bytes,
            "sc-min-posts-interval-ms": config.sc_min_posts_interval_ms,
            "reuse-settings": self._mihomo_reuse_settings(config.xmux),
            "download-settings": self._mihomo_download_settings(config.download_settings),
        }

        if random_user_agent:
            headers = result.get("headers") or {}
            user_agents = (
                self.grpc_user_agent_data
                if config.mode in ("stream-one", "stream-up") and not config.no_grpc_header
                else self.user_agent_list
            )
            if user_agents:
                headers["User-Agent"] = choice(user_agents)
                result["headers"] = headers

        return self._normalize_mihomo_xhttp_opts(result)

    @staticmethod
    def _select_host(host: list[str] | str) -> str:
        if isinstance(host, str):
            return host
        if host:
            return host[0]
        return ""

    def _mihomo_download_settings(self, download_settings: SubscriptionInboundData | dict | None) -> dict | None:
        if isinstance(download_settings, SubscriptionInboundData):
            return self._mihomo_download_settings_from_inbound(download_settings)

        if isinstance(download_settings, dict):
            if "streamSettings" in download_settings or "address" in download_settings:
                return self._mihomo_download_settings_from_xray(download_settings)
            return self._normalize_mihomo_xhttp_opts(download_settings)

        return None

    def _mihomo_download_settings_from_xray(self, download_settings: dict) -> dict:
        stream_settings = download_settings.get("streamSettings") or {}
        if not isinstance(stream_settings, dict):
            stream_settings = {}

        xhttp_settings = download_settings.get("xhttpSettings") or stream_settings.get("xhttpSettings") or {}
        if not isinstance(xhttp_settings, dict):
            xhttp_settings = {}

        extra = xhttp_settings.get("extra") or {}
        if not isinstance(extra, dict):
            extra = {}

        security = download_settings.get("security") or stream_settings.get("security")
        tls_settings = download_settings.get(f"{security}Settings") or stream_settings.get(f"{security}Settings") or {}
        if not isinstance(tls_settings, dict):
            tls_settings = {}

        result = {
            "path": xhttp_settings.get("path"),
            "host": xhttp_settings.get("host"),
            "headers": self._mihomo_http_headers(extra.get("headers")),
            "reuse-settings": self._mihomo_reuse_settings(extra.get("xmux")),
            "server": download_settings.get("address"),
            "port": self._select_port(download_settings.get("port")),
            "tls": True if security and security != "none" else None,
            "alpn": tls_settings.get("alpn"),
            "skip-cert-verify": tls_settings.get("allowInsecure"),
            "servername": tls_settings.get("serverName"),
            "client-fingerprint": tls_settings.get("fingerprint"),
            "reality-opts": {
                "public-key": tls_settings.get("publicKey"),
                "short-id": tls_settings.get("shortId") or "",
                "support-x25519mlkem768": bool(tls_settings.get("mldsa65Verify")),
            }
            if security == "reality" and tls_settings.get("publicKey")
            else None,
        }

        return self._normalize_mihomo_xhttp_opts(result)

    def _mihomo_download_settings_from_inbound(self, inbound: SubscriptionInboundData) -> dict:
        transport_config = inbound.transport_config
        result = {
            "server": self._select_address(inbound.address),
            "port": self._select_port(inbound.port),
        }

        if inbound.network in ("xhttp", "splithttp") and isinstance(transport_config, XHTTPTransportConfig):
            result.update(
                {
                    "path": transport_config.path or "/",
                    "host": self._select_host(transport_config.host),
                    "headers": self._mihomo_http_headers(transport_config.http_headers),
                    "reuse-settings": self._mihomo_reuse_settings(transport_config.xmux),
                }
            )

        self._apply_mihomo_download_tls(result, inbound.tls_config)

        return self._normalize_mihomo_xhttp_opts(result)

    @staticmethod
    def _mihomo_http_headers(headers: dict | None) -> dict | None:
        if not headers:
            return None

        filtered_headers = {k: v for k, v in headers.items() if k not in ("Host", "host")}
        return filtered_headers or None

    @staticmethod
    def _select_address(address: list[str] | str) -> str:
        if isinstance(address, str):
            return address
        if address:
            return address[0]
        return ""

    def _apply_mihomo_download_tls(self, node: dict, tls_config: TLSConfig):
        if not tls_config.tls:
            return

        node["tls"] = True
        sni = tls_config.sni if isinstance(tls_config.sni, str) else (tls_config.sni[0] if tls_config.sni else "")
        node["servername"] = sni

        if tls_config.alpn_list:
            node["alpn"] = tls_config.alpn_list

        node["skip-cert-verify"] = tls_config.allowinsecure

        if tls_config.fingerprint:
            node["client-fingerprint"] = tls_config.fingerprint

        if tls_config.tls == "reality" and tls_config.reality_public_key:
            node["reality-opts"] = {
                "public-key": tls_config.reality_public_key,
                "short-id": tls_config.reality_short_id or "",
                "support-x25519mlkem768": bool(tls_config.mldsa65_verify),
            }

    @staticmethod
    def _mihomo_reuse_settings(xmux: dict | BaseModel | None) -> dict | None:
        """Convert Xray XMUX settings to Mihomo reuse-settings."""
        if not xmux:
            return None

        if isinstance(xmux, BaseModel):
            xmux = xmux.model_dump(by_alias=True, exclude_none=True)

        key_map = {
            "maxConcurrency": "max-concurrency",
            "max_concurrency": "max-concurrency",
            "maxConnections": "max-connections",
            "max_connections": "max-connections",
            "cMaxReuseTimes": "c-max-reuse-times",
            "c_max_reuse_times": "c-max-reuse-times",
            "hMaxRequestTimes": "h-max-request-times",
            "h_max_request_times": "h-max-request-times",
            "hMaxReusableSecs": "h-max-reusable-secs",
            "h_max_reusable_secs": "h-max-reusable-secs",
            "hKeepAlivePeriod": "h-keep-alive-period",
            "h_keep_alive_period": "h-keep-alive-period",
        }
        result = {key_map.get(key, key): value for key, value in xmux.items()}

        return ClashConfiguration._normalize_mihomo_xhttp_opts(result)

    @staticmethod
    def _normalize_mihomo_xhttp_opts(data: dict) -> dict:
        """Remove empty values while preserving explicit False and 0 values supported by Mihomo."""

        def clean_dict(value: dict) -> dict:
            cleaned = {}
            for key, item in value.items():
                if item is None or item == "":
                    continue
                if key == "headers" and isinstance(item, dict):
                    headers = {
                        header_key: header_value
                        for header_key, header_value in item.items()
                        if header_value is not None
                    }
                    if headers:
                        cleaned[key] = headers
                    continue
                if isinstance(item, dict):
                    nested = clean_dict(item)
                    if nested:
                        cleaned[key] = nested
                    continue
                if isinstance(item, BaseModel):
                    item = item.model_dump(by_alias=True, exclude_none=True)
                cleaned[key] = item
            return cleaned

        return clean_dict(data)

    def _apply_tls(self, node: dict, tls_config: TLSConfig, protocol: str):
        """Apply TLS settings to node"""
        if not tls_config.tls:
            return

        node["tls"] = True
        sni = tls_config.sni if isinstance(tls_config.sni, str) else ""

        if protocol in ("trojan", "hysteria"):
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
        elif network == "http" or network == "xhttp":
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
    def _select_port(port: int | str | list[int] | list[str] | None) -> int | None:
        """Normalize port values from subscription data."""
        if port is None:
            return None
        if isinstance(port, list):
            if not port:
                return None
            port = port[0]
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

        if flow := inbound.inbound_flow:
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
        if inbound.network == "kcp":
            return
        if inbound.network in ("splithttp", "xhttp") and inbound.protocol != "vless":
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
