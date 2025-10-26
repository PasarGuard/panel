import json
from random import choice

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
from app.templates import render_template
from app.utils.helpers import UUIDEncoder
from config import XRAY_SUBSCRIPTION_TEMPLATE

from . import BaseSubscription


class XrayConfiguration(BaseSubscription):
    def __init__(self):
        super().__init__()
        self.config = []
        self.template = render_template(XRAY_SUBSCRIPTION_TEMPLATE)

        # Registry for transport handlers
        self.transport_handlers = {
            "ws": self._transport_ws,
            "httpupgrade": self._transport_httpupgrade,
            "splithttp": self._transport_xhttp,
            "xhttp": self._transport_xhttp,
            "grpc": self._transport_grpc,
            "gun": self._transport_grpc,
            "tcp": self._transport_tcp,
            "kcp": self._transport_kcp,
            "quic": self._transport_quic,
            "h2": self._transport_http,
        }

        # Registry for protocol builders
        self.protocol_handlers = {
            "vmess": self._build_vmess,
            "vless": self._build_vless,
            "trojan": self._build_trojan,
            "shadowsocks": self._build_shadowsocks,
        }

    def add_config(self, remarks, outbounds):
        json_template = json.loads(self.template)
        json_template["remarks"] = remarks
        json_template["outbounds"] = outbounds + json_template["outbounds"]
        self.config.append(json_template)

    def render(self, reverse=False):
        if reverse:
            self.config.reverse()
        return json.dumps(self.config, indent=4, cls=UUIDEncoder)

    def add(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict):
        """Add outbound using registry pattern"""

        # Get protocol handler from registry
        handler = self.protocol_handlers.get(inbound.protocol)
        if not handler:
            return

        # Build outbound(s)
        result = handler(remark=remark, address=address, inbound=inbound, settings=settings)
        if not result:
            return

        # Handle different return types
        if isinstance(result, tuple):
            # VMess, VLESS, Trojan return (main_outbound, extra_outbounds_list)
            main_outbound, extra_outbounds = result
            all_outbounds = [main_outbound] + extra_outbounds
        else:
            # Shadowsocks returns just a dict
            all_outbounds = [result]

        self.add_config(remarks=remark, outbounds=all_outbounds)

    # ========== Transport Handlers (Registry Methods) ==========

    def _transport_ws(self, config: WebSocketTransportConfig, path: str) -> dict:
        """Handle WebSocket transport - only gets WS config"""
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")

        ws_settings = {
            "headers": config.http_headers if config.http_headers else {},
            "heartbeatPeriod": config.heartbeat_period,
            "path": path,
            "host": host,
        }

        if config.random_user_agent:
            ws_settings["headers"]["User-Agent"] = choice(self.user_agent_list)

        return self._normalize_and_remove_none_values(ws_settings)

    def _transport_httpupgrade(self, config: WebSocketTransportConfig, path: str) -> dict:
        """Handle HTTPUpgrade transport - only gets WS config"""
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")

        httpupgrade_settings = {
            "headers": config.http_headers if config.http_headers else {},
            "path": path,
            "host": host,
        }

        if config.random_user_agent:
            httpupgrade_settings["headers"]["User-Agent"] = choice(self.user_agent_list)

        return self._normalize_and_remove_none_values(httpupgrade_settings)

    def _transport_xhttp(self, config: XHTTPTransportConfig, path: str) -> dict:
        """Handle xHTTP/SplitHTTP transport - only gets xHTTP config"""
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")

        xhttp_settings = {
            "mode": config.mode,
            "path": path if path else None,
            "host": host if host else None,
        }

        extra = {
            "headers": config.http_headers if config.http_headers else {},
            "scMaxEachPostBytes": config.sc_max_each_post_bytes,
            "scMinPostsIntervalMs": config.sc_min_posts_interval_ms,
            "xPaddingBytes": config.x_padding_bytes,
            "noGRPCHeader": config.no_grpc_header,
            "xmux": config.xmux,
            "downloadSettings": self._download_config(config.download_settings) if config.download_settings else None,
        }

        if config.random_user_agent:
            if config.mode in ("stream-one", "stream-up") and not config.no_grpc_header:
                extra["headers"]["User-Agent"] = choice(self.grpc_user_agent_data)
            else:
                extra["headers"]["User-Agent"] = choice(self.user_agent_list)

        xhttp_settings["extra"] = extra
        return self._normalize_and_remove_none_values(xhttp_settings)

    def _transport_grpc(self, config: GRPCTransportConfig, path: str) -> dict:
        """Handle GRPC transport - only gets GRPC config"""
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")

        grpc_settings = {
            "idle_timeout": config.idle_timeout if config.idle_timeout is not None else 60,
            "health_check_timeout": config.health_check_timeout if config.health_check_timeout is not None else 20,
            "permit_without_stream": config.permit_without_stream,
            "initial_windows_size": config.initial_windows_size if config.initial_windows_size is not None else 35538,
            "serviceName": path,
            "authority": host,
            "multiMode": config.multi_mode,
        }

        if config.http_headers and "user-agent" in config.http_headers:
            grpc_settings["user_agent"] = config.http_headers["user-agent"]

        if config.random_user_agent:
            grpc_settings["user_agent"] = choice(self.grpc_user_agent_data)

        return self._normalize_and_remove_none_values(grpc_settings)

    def _transport_tcp(self, config: TCPTransportConfig, path: str) -> dict:
        """Handle TCP transport - only gets TCP config"""
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")
        headers = config.header_type

        if headers == "http":
            tcp_settings = {
                "header": {
                    "type": headers,
                    "request": config.request
                    if config.request
                    else {
                        "version": "1.1",
                        "method": "GET",
                        "path": ["/"],
                        "headers": {
                            "Host": [],
                            "User-Agent": [],
                            "Accept-Encoding": ["gzip, deflate"],
                            "Connection": ["keep-alive"],
                            "Pragma": "no-cache",
                        },
                    },
                    "response": config.response
                    if config.response
                    else {
                        "version": "1.1",
                        "status": "200",
                        "reason": "OK",
                        "headers": {
                            "Content-Type": ["application/octet-stream", "video/mpeg"],
                            "Transfer-Encoding": ["chunked"],
                            "Connection": ["keep-alive"],
                            "Pragma": "no-cache",
                        },
                    },
                }
            }
        else:
            tcp_settings = {"header": {"type": headers}}

        if any((path, host, config.random_user_agent)):
            if "request" not in tcp_settings["header"]:
                tcp_settings["header"]["request"] = {}

        if any((config.random_user_agent, host)):
            if (
                "headers" not in tcp_settings["header"]["request"]
                or tcp_settings["header"]["request"]["headers"] is None
            ):
                tcp_settings["header"]["request"]["headers"] = {}

        if path:
            tcp_settings["header"]["request"]["path"] = [path]

        if host:
            tcp_settings["header"]["request"]["headers"]["Host"] = [host]

        if config.random_user_agent:
            tcp_settings["header"]["request"]["headers"]["User-Agent"] = [choice(self.user_agent_list)]

        return self._normalize_and_remove_none_values(tcp_settings)

    def _transport_http(self, config: TCPTransportConfig, path: str) -> dict:
        """Handle HTTP (h2) transport - only gets TCP config"""
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")

        http_settings = {
            "headers": {k: [v] for k, v in config.http_headers.items()} if config.http_headers else {},
            "path": path,
            "host": [host] if host else [],
        }

        if config.random_user_agent:
            http_settings["headers"]["User-Agent"] = [choice(self.user_agent_list)]

        return self._normalize_and_remove_none_values(http_settings)

    def _transport_quic(self, config: QUICTransportConfig, path: str) -> dict:
        """Handle QUIC transport - only gets QUIC config"""
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")

        return self._normalize_and_remove_none_values({
            "security": host,
            "header": {"type": config.header_type},
            "key": path,
        })

    def _transport_kcp(self, config: KCPTransportConfig, path: str) -> dict:
        """Handle KCP transport - only gets KCP config"""
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")

        return self._normalize_and_remove_none_values({
            "header": {"type": config.header_type, "domain": host},
            "mtu": config.mtu if config.mtu else 1350,
            "tti": config.tti if config.tti else 50,
            "uplinkCapacity": config.uplink_capacity if config.uplink_capacity else 12,
            "downlinkCapacity": config.downlink_capacity if config.downlink_capacity else 100,
            "congestion": config.congestion,
            "readBufferSize": config.read_buffer_size if config.read_buffer_size else 2,
            "writeBufferSize": config.write_buffer_size if config.write_buffer_size else 2,
            "seed": path,
        })

    def _apply_transport(self, network: str, inbound: SubscriptionInboundData, path: str) -> dict | None:
        """Apply transport settings using registry pattern"""
        handler = self.transport_handlers.get(network)
        if not handler:
            return None

        # Use stored config instance
        return handler(inbound.transport_config, path)

    def _apply_tls(self, tls_config: TLSConfig, security: str) -> dict:
        """Apply TLS/Reality settings - only receives TLS config"""
        sni = tls_config.sni if isinstance(tls_config.sni, str) else (tls_config.sni[0] if tls_config.sni else None)

        if security == "reality":
            return self._normalize_and_remove_none_values({
                "serverName": sni,
                "fingerprint": tls_config.fingerprint,
                "show": False,
                "publicKey": tls_config.reality_public_key,
                "shortId": tls_config.reality_short_id,
                "spiderX": tls_config.reality_spx,
                "mldsa65Verify": tls_config.mldsa65_verify,
            })
        else:  # tls
            config = {
                "serverName": sni,
                "allowInsecure": tls_config.allowinsecure,
                "show": False,
                "fingerprint": tls_config.fingerprint,
                "echConfigList": tls_config.ech_config_list,
            }
            if tls_config.alpn_list:
                config["alpn"] = tls_config.alpn_list  # Use list for xray

            return self._normalize_and_remove_none_values(config)

    def make_dialer_outbound(
        self, fragment: dict | None = None, noises: dict | None = None, dialer_tag: str = "dialer"
    ) -> dict | None:
        """
        Create Freedom protocol outbound with fragment/noise settings.
        This is the CORRECT way to handle fragment/noise in xray-core.
        """
        xray_noises = noises.get("xray", []) if noises else []
        dialer_settings = {
            "fragment": fragment.get("xray") if fragment else None,
            "noises": [{self.snake_to_camel(k): v for k, v in noise.items()} for noise in xray_noises] or None,
        }
        dialer_settings = self._normalize_and_remove_none_values(dialer_settings)

        if dialer_settings:
            return {"tag": dialer_tag, "protocol": "freedom", "settings": dialer_settings}

    def _download_config(self, download_settings: SubscriptionInboundData, link_format: bool = False) -> dict:
        """Build download settings block for xHTTP transports"""

        network = download_settings.network
        path = download_settings.transport_config.path
        if network in ("grpc", "gun"):
            if getattr(download_settings.transport_config, "multi_mode", False):
                path = self.get_grpc_multi(path)
            else:
                path = self.get_grpc_gun(path)

        network_setting = self._apply_transport(network, download_settings, path)

        security = download_settings.tls_config.tls
        security = security if security and security != "none" else None
        tls_settings = self._apply_tls(download_settings.tls_config, security) if security else None

        dialer_proxy = ""
        if (download_settings.fragment_settings or download_settings.noise_settings) and not link_format:
            dialer_proxy = "dsdialer"
        if dialer_proxy:
            sockopt = {"dialerProxy": dialer_proxy}
        else:
            sockopt = None

        stream_settings = self._stream_setting_config(
            network=network,
            security=security,
            network_setting=network_setting,
            tls_settings=tls_settings,
            sockopt=sockopt,
        )

        return self._normalize_and_remove_none_values({
            "address": download_settings.address,
            "port": self._select_port(download_settings.port),
            **stream_settings,
        })

    # ========== Protocol Builders (Registry Methods) ==========

    def _build_vmess(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> tuple:
        """Build VMess outbound - returns (main_outbound, extra_outbounds_list)"""
        return self._build_outbound(
            protocol_type="vmess",
            address=address,
            inbound=inbound,
            user_settings={"id": str(settings["id"]), "alterId": 0, "security": "auto"},
        )

    def _build_vless(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> tuple:
        """Build VLESS outbound - returns (main_outbound, extra_outbounds_list)"""
        flow = settings.get("flow", "")
        user_settings = {"id": str(settings["id"]), "encryption": inbound.encryption}
        if flow:
            user_settings["flow"] = flow

        return self._build_outbound(
            protocol_type="vless",
            address=address,
            inbound=inbound,
            user_settings=user_settings,
        )

    def _build_trojan(self, remark: str, address: str, inbound: SubscriptionInboundData, settings: dict) -> tuple:
        """Build Trojan outbound - returns (main_outbound, extra_outbounds_list)"""
        flow = settings.get("flow", "")
        user_settings = {"password": settings["password"]}
        if flow:
            user_settings["flow"] = flow

        return self._build_outbound(
            protocol_type="trojan",
            address=address,
            inbound=inbound,
            user_settings=user_settings,
        )

    def _build_shadowsocks(self, address: str, remark: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build Shadowsocks outbound"""
        method, password = self.detect_shadowsocks_2022(
            inbound.is_2022,
            inbound.method,
            settings["method"],
            getattr(inbound, "password", None),
            settings["password"],
        )

        outbound = {
            "protocol": "shadowsocks",
            "tag": "proxy",
            "settings": {
                "servers": [
                    {
                        "address": address,
                        "port": self._select_port(inbound.port),
                        "password": password,
                        "method": method,
                    }
                ]
            },
        }

        return self._normalize_and_remove_none_values(outbound)

    def _build_outbound(
        self,
        protocol_type: str,
        address: str,
        inbound: SubscriptionInboundData,
        user_settings: dict,
    ) -> dict:
        """Generic outbound builder"""
        network = inbound.network
        path = inbound.transport_config.path

        # Process GRPC path
        if network in ("grpc", "gun"):
            if getattr(inbound.transport_config, "multi_mode", False):
                path = self.get_grpc_multi(path)
            else:
                path = self.get_grpc_gun(path)

        outbound = {
            "protocol": protocol_type,
            "tag": "proxy",
            "settings": {
                "vnext" if protocol_type in ("vmess", "vless") else "servers": [
                    {
                        "address": address,
                        "port": self._select_port(inbound.port),
                        "users": [user_settings],
                    }
                ]
            },
        }

        # Build stream settings
        network_setting = self._apply_transport(network, inbound, path)

        security = inbound.tls_config.tls if inbound.tls_config.tls != "none" else None
        tls_settings = self._apply_tls(inbound.tls_config, security) if security else None

        # Handle fragment/noise - create dialer outbound
        extra_outbounds = []
        sockopt = None
        if inbound.fragment_settings or inbound.noise_settings:
            dialer_outbound = self.make_dialer_outbound(inbound.fragment_settings, inbound.noise_settings, "dialer")
            if dialer_outbound:
                extra_outbounds.append(dialer_outbound)
                sockopt = {"dialerProxy": "dialer"}

        outbound["streamSettings"] = self._stream_setting_config(
            network=network,
            security=security,
            network_setting=network_setting,
            tls_settings=tls_settings,
            sockopt=sockopt,
        )

        # Add mux
        if inbound.mux_settings and (xray_mux := inbound.mux_settings.get("xray")):
            outbound["mux"] = xray_mux

        return self._normalize_and_remove_none_values(outbound), extra_outbounds

    @staticmethod
    def _stream_setting_config(
        network=None, security=None, network_setting=None, tls_settings=None, sockopt=None
    ) -> dict:
        """Build stream settings"""
        stream_settings = {"network": network}

        if security and security != "none":
            stream_settings["security"] = security
            stream_settings[f"{security}Settings"] = tls_settings

        if network and network_setting:
            stream_settings[f"{network}Settings"] = network_setting

        if sockopt:
            stream_settings["sockopt"] = sockopt

        return stream_settings

    def _select_port(self, port: int | str) -> int:
        """Select a random port if multiple are provided"""
        if isinstance(port, str):
            ports = port.split(",")
            return int(choice(ports))
        return port
