import json
import re
from copy import deepcopy
from dataclasses import dataclass
from itertools import chain
from random import choice

from pydantic import BaseModel

from app.models.host import FinalMask, dump_final_mask_for_xray
from app.models.subscription import (
    GRPCTransportConfig,
    KCPTransportConfig,
    MasqueProtocolData,
    MasqueTransportConfig,
    QUICTransportConfig,
    SubscriptionInboundData,
    TCPTransportConfig,
    TLSConfig,
    WebSocketTransportConfig,
    XDriveTransportConfig,
    XHTTPTransportConfig,
)

from . import BaseSubscription
from .base import dumps_compact
from .template_directives import DIRECTIVE_KEY, HostCandidate, XrayDirective, parse_xray_directive

SINGLE_CONFIG_DEFAULT_REMARKS = "PasarGuard"


@dataclass(slots=True)
class _XrayHost:
    candidate: HostCandidate
    outbounds: list[dict]


@dataclass(slots=True)
class _DirectiveConfig:
    """A config whose template has a pasarguard directive; built in render() once every host is known."""

    host_index: int
    template: dict
    directive: XrayDirective


class XrayConfiguration(BaseSubscription):
    def __init__(
        self,
        xray_template_content: str | None = None,
        user_agent_template_content: str | None = None,
        grpc_user_agent_template_content: str | None = None,
        single_remarks: str | None = None,
    ):
        """Initialize an empty subscription builder from optional JSON templates.

        The Xray template is the base for each added configuration. The user
        agent templates provide lists for transports that select user agents.
        Missing or empty template content uses empty defaults. Malformed JSON
        in any template propagates as ``json.JSONDecodeError``.
        """
        super().__init__(
            user_agent_template_content=user_agent_template_content,
            grpc_user_agent_template_content=grpc_user_agent_template_content,
        )
        self.config = []
        self.template = json.loads(xray_template_content) if xray_template_content else {}
        # Remarks of the one config a "single" mode template produces (the subscription profile title).
        self.single_remarks = single_remarks
        self._hosts: list[_XrayHost] = []
        self._directives: dict[str | None, XrayDirective | None] = {}
        self._single_templates: set[str | None] = set()
        self._has_directive_configs = False

        # Registry for transport handlers
        self.transport_handlers = {
            "ws": self._transport_ws,
            "httpupgrade": self._transport_httpupgrade,
            "splithttp": self._transport_xhttp,
            "xhttp": self._transport_xhttp,
            "xdrive": self._transport_xdrive,
            "quic": self._transport_quic,
            "grpc": self._transport_grpc,
            "gun": self._transport_grpc,
            "tcp": self._transport_tcp,
            "raw": self._transport_tcp,
            "kcp": self._transport_kcp,
            "h2": self._transport_http,
            "masque": self._transport_masque,
        }

        # Registry for protocol builders
        self.protocol_handlers = {
            "vmess": self._build_vmess,
            "vless": self._build_vless,
            "trojan": self._build_trojan,
            "shadowsocks": self._build_shadowsocks,
            "hysteria": self._build_hysteria,
            "masque": self._build_masque,
            "wireguard": self._build_wireguard,
        }

    def add_config(self, remarks, outbounds, template_content: str | None = None):
        json_template = json.loads(template_content) if template_content is not None else self.template.copy()
        if DIRECTIVE_KEY in json_template:
            directive = self._template_directive(template_content, json_template.pop(DIRECTIVE_KEY))
            if directive is not None and self._hosts:
                if directive.mode == "single":
                    # One config per template, placed where its first host would be.
                    if template_content in self._single_templates:
                        return
                    self._single_templates.add(template_content)
                self.config.append(_DirectiveConfig(len(self._hosts) - 1, json_template, directive))
                self._has_directive_configs = True
                return
        json_template["remarks"] = remarks
        json_template["outbounds"] = outbounds + json_template["outbounds"]
        self.config.append(json_template)

    def _template_directive(self, template_content: str | None, raw_directive) -> XrayDirective | None:
        if template_content not in self._directives:
            self._directives[template_content] = parse_xray_directive(raw_directive)
        return self._directives[template_content]

    def render(self):
        if not self._has_directive_configs:
            return dumps_compact(self.config)
        return dumps_compact(
            [self._build_directive_config(item) if isinstance(item, _DirectiveConfig) else item for item in self.config]
        )

    def _build_directive_config(self, item: _DirectiveConfig) -> dict:
        json_template = dict(item.template)
        template_outbounds = json_template.get("outbounds") or []
        used_tags = {outbound.get("tag") for outbound in template_outbounds if isinstance(outbound, dict)}

        if item.directive.mode == "single":
            outbounds = []
            skip_index = None
            json_template["remarks"] = (
                self.single_remarks or json_template.get("remarks") or SINGLE_CONFIG_DEFAULT_REMARKS
            )
        else:
            host = self._hosts[item.host_index]
            outbounds = list(host.outbounds)
            used_tags.update(outbound.get("tag") for outbound in outbounds)
            skip_index = item.host_index
            json_template["remarks"] = host.candidate.remark

        injected: list[tuple[_XrayHost, str]] = []
        # Balancers and observatories select outbounds by tag prefix, so helper outbounds (freedom dialers that
        # go direct) must never start with an injected tag or tag prefix.
        reserved_prefixes: set[str] = set()
        for inject in item.directive.inject:
            selected = [
                host
                for index, host in enumerate(self._hosts)
                if index != skip_index and inject.select.matches(host.candidate)
            ]
            if inject.tag_prefix or inject.tag_from == "index":
                reserved_prefixes.add(inject.tag_prefix or "proxy")
            for number, host in enumerate(selected, start=1):
                if inject.tag_from == "remark":
                    name = self._sanitize_tag(host.candidate.remark) or str(number)
                    base_tag = f"{inject.tag_prefix}-{name}" if inject.tag_prefix else name
                else:
                    base_tag = f"{inject.tag_prefix or 'proxy'}-{number}"
                reserved_prefixes.add(base_tag)
                injected.append((host, base_tag))

        if skip_index is not None:
            outbounds = self._retag_outbounds(outbounds, None, used_tags, reserved_prefixes)
        for host, base_tag in injected:
            outbounds.extend(self._retag_outbounds(host.outbounds, base_tag, used_tags, reserved_prefixes))

        json_template["outbounds"] = outbounds + template_outbounds
        return json_template

    @staticmethod
    def _sanitize_tag(remark: str) -> str:
        return re.sub(r"[^\w.-]+", "-", remark).strip("-")

    @staticmethod
    def _unique_tag(base_tag: str, used_tags: set) -> str:
        tag = base_tag
        suffix = 2
        while tag in used_tags:
            tag = f"{base_tag}-{suffix}"
            suffix += 1
        used_tags.add(tag)
        return tag

    @staticmethod
    def _helper_tag(old_tag: str, main_tag: str, reserved_prefixes: set[str]) -> str:
        """Tag for a helper outbound that no balancer/observatory prefix selector of the injected tags matches."""
        base = f"{old_tag}-{main_tag}"
        if not any(base.startswith(prefix) for prefix in reserved_prefixes):
            return base
        taken_first_chars = {prefix[0] for prefix in reserved_prefixes if prefix}
        candidates = chain("_~", map(chr, range(0x21, 0x110000)))
        lead = next(char for char in candidates if char not in taken_first_chars)
        return f"{lead}{base}"

    @classmethod
    def _retag_outbounds(
        cls, outbounds: list[dict], base_tag: str | None, used_tags: set, reserved_prefixes: set[str]
    ) -> list[dict]:
        """Copy a host's outbounds, the main one under ``base_tag`` (None keeps it); helper outbounds
        (fragment/noise dialer) get tags outside ``reserved_prefixes`` and dialerProxy references follow them."""
        main, *helpers = deepcopy(outbounds)
        if base_tag is not None:
            main["tag"] = cls._unique_tag(base_tag, used_tags)
        renamed = {}
        for helper in helpers:
            old_tag = helper.get("tag")
            if base_tag is None and not any(str(old_tag).startswith(prefix) for prefix in reserved_prefixes):
                continue
            helper["tag"] = cls._unique_tag(cls._helper_tag(old_tag, main["tag"], reserved_prefixes), used_tags)
            renamed[old_tag] = helper["tag"]
        if renamed:
            cls._rename_dialer_proxies(main, renamed)
        return [main, *helpers]

    @classmethod
    def _rename_dialer_proxies(cls, value, renamed: dict[str, str]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "dialerProxy" and item in renamed:
                    value[key] = renamed[item]
                else:
                    cls._rename_dialer_proxies(item, renamed)
        elif isinstance(value, list):
            for item in value:
                cls._rename_dialer_proxies(item, renamed)

    def add(
        self,
        remark: str,
        address: str,
        inbound: SubscriptionInboundData,
        settings: dict,
        template_content: str | None = None,
        host_id: int | None = None,
    ):
        """Add outbound using registry pattern"""

        # Get protocol handler from registry
        handler = self.protocol_handlers.get(inbound.protocol)
        if not handler:
            return

        # Build outbound(s)
        result = handler(address=address, inbound=inbound, settings=settings)
        if not result:
            return

        # Handle different return types
        if isinstance(result, tuple):
            # VMess, VLESS, Trojan, Shadowsocks, WireGuard return (main_outbound, extra_outbounds_list)
            main_outbound, extra_outbounds = result
            all_outbounds = [main_outbound] + extra_outbounds
        else:
            all_outbounds = [result]

        self._hosts.append(_XrayHost(HostCandidate(host_id, inbound.inbound_tag, remark), all_outbounds))
        self.add_config(remarks=remark, outbounds=all_outbounds, template_content=template_content)

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
            "xPaddingObfsMode": config.x_padding_obfs_mode,
            "xPaddingKey": config.x_padding_key,
            "xPaddingHeader": config.x_padding_header,
            "xPaddingPlacement": config.x_padding_placement,
            "xPaddingMethod": config.x_padding_method,
            "uplinkHTTPMethod": config.uplink_http_method,
            "sessionIDPlacement": config.session_placement,
            "sessionIDKey": config.session_key,
            "sessionIDTable": config.session_id_table,
            "sessionIDLength": config.session_id_length,
            "seqPlacement": config.seq_placement,
            "seqKey": config.seq_key,
            "uplinkDataPlacement": config.uplink_data_placement,
            "uplinkDataKey": config.uplink_data_key,
            "uplinkChunkSize": config.uplink_chunk_size,
            "noGRPCHeader": config.no_grpc_header,
            "xmux": config.xmux,
            "downloadSettings": self._xhttp_download_config(config.download_settings)
            if config.download_settings
            else None,
        }

        if config.random_user_agent:
            if config.mode in ("stream-one", "stream-up") and not config.no_grpc_header:
                extra["headers"]["User-Agent"] = choice(self.grpc_user_agent_data)
            else:
                extra["headers"]["User-Agent"] = choice(self.user_agent_list)

        xhttp_settings["extra"] = extra
        return self._normalize_and_remove_none_values(xhttp_settings)

    @staticmethod
    def _transport_xdrive(config: XDriveTransportConfig, path: str) -> dict:
        """Build XDrive transport settings using Xray's camelCase JSON keys."""
        return config.model_dump(by_alias=True, exclude_none=True, exclude={"path", "host"})

    def _xhttp_download_config(self, download_settings: SubscriptionInboundData | dict) -> dict:
        if isinstance(download_settings, dict):
            return download_settings
        return self._download_config(download_settings)

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

        if any((path, host, config.random_user_agent)) and "request" not in tcp_settings["header"]:
            tcp_settings["header"]["request"] = {}

        if any((config.random_user_agent, host)) and (
            "headers" not in tcp_settings["header"]["request"] or tcp_settings["header"]["request"]["headers"] is None
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

    def _transport_masque(self, config: MasqueTransportConfig, path: str) -> dict:
        """Build MASQUE transport settings using the supplied path.

        Use the first host when multiple hosts are supplied, and omit an empty
        host, path, or header mapping from the returned settings.
        """
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")
        return self._normalize_and_remove_none_values(
            {
                "host": host,
                "path": path or None,
                "headers": config.http_headers or None,
                "xmux": config.xmux or None,
            }
        )

    def _transport_quic(self, config: QUICTransportConfig, path: str) -> dict:
        """Handle QUIC transport - only gets QUIC config"""
        host = config.host if isinstance(config.host, str) else (config.host[0] if config.host else "")

        return self._normalize_and_remove_none_values(
            {
                "security": host,
                "header": {"type": config.header_type},
                "key": path,
            }
        )

    def _transport_kcp(self, config: KCPTransportConfig, path: str) -> dict:
        """Handle KCP transport - only gets KCP config"""
        return self._normalize_and_remove_none_values(
            {
                "mtu": config.mtu if config.mtu is not None else 1350,
                "tti": config.tti if config.tti is not None else 50,
                "uplinkCapacity": config.uplink_capacity if config.uplink_capacity is not None else 5,
                "downlinkCapacity": config.downlink_capacity if config.downlink_capacity is not None else 20,
                "congestion": config.congestion,
                "readBufferSize": config.read_buffer_size if config.read_buffer_size is not None else 2,
                "writeBufferSize": config.write_buffer_size if config.write_buffer_size is not None else 2,
            }
        )

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
            return self._normalize_and_remove_none_values(
                {
                    "serverName": sni,
                    "fingerprint": tls_config.fingerprint,
                    "show": False,
                    "publicKey": tls_config.reality_public_key,
                    "shortId": tls_config.reality_short_id,
                    "spiderX": tls_config.reality_spx,
                    "mldsa65Verify": tls_config.mldsa65_verify,
                }
            )
        else:  # tls
            config = {
                "serverName": sni,
                "allowInsecure": tls_config.allowinsecure,
                "show": False,
                "fingerprint": tls_config.fingerprint,
                "echConfigList": tls_config.ech_config_list,
                "echForceQuery": tls_config.ech_query_strategy,
                "pinnedPeerCertSha256": tls_config.pinned_peer_cert_sha256,
                "verifyPeerCertByName": ",".join(tls_config.verify_peer_cert_by_name)
                if tls_config.verify_peer_cert_by_name
                else "",
                "cipherSuites": tls_config.cipher_suites if tls_config.fingerprint == "unsafe" else "",
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

        return self._normalize_and_remove_none_values(
            {
                "address": download_settings.address,
                "port": self._select_port(download_settings.port),
                **stream_settings,
            }
        )

    # ========== Protocol Builders (Registry Methods) ==========

    def _build_vmess(self, address: str, inbound: SubscriptionInboundData, settings: dict) -> tuple:
        """Build VMess outbound - returns (main_outbound, extra_outbounds_list)"""
        return self._build_outbound(
            protocol_type="vmess",
            address=address,
            inbound=inbound,
            user_settings={"id": str(settings["id"]), "alterId": 0, "security": "auto"},
        )

    def _build_vless(self, address: str, inbound: SubscriptionInboundData, settings: dict) -> tuple:
        """Build VLESS outbound - returns (main_outbound, extra_outbounds_list)"""
        # Handle vless-route if needed (only affects ID)
        id = str(settings["id"])
        if inbound.vless_route:
            id = self.vless_route(id, inbound.vless_route)

        user_settings = {"id": id, "encryption": inbound.encryption}

        if flow := inbound.inbound_flow:
            user_settings["flow"] = flow

        return self._build_outbound(
            protocol_type="vless",
            address=address,
            inbound=inbound,
            user_settings=user_settings,
        )

    def _build_trojan(self, address: str, inbound: SubscriptionInboundData, settings: dict) -> tuple:
        """Build Trojan outbound - returns (main_outbound, extra_outbounds_list)"""
        user_settings = {"password": settings["password"]}

        return self._build_outbound(
            protocol_type="trojan",
            address=address,
            inbound=inbound,
            user_settings=user_settings,
        )

    def _build_shadowsocks(self, address: str, inbound: SubscriptionInboundData, settings: dict) -> tuple:
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

        # Handle fragment/noise - create dialer outbound
        extra_outbounds = []
        sockopt = None
        if inbound.fragment_settings or inbound.noise_settings:
            dialer_outbound = self.make_dialer_outbound(inbound.fragment_settings, inbound.noise_settings, "dialer")
            if dialer_outbound:
                extra_outbounds.append(dialer_outbound)
                sockopt = {"dialerProxy": "dialer"}

        if sockopt or inbound.finalmask:
            outbound["streamSettings"] = self._stream_setting_config(
                network=inbound.network,
                sockopt=sockopt,
                finalmask=inbound.finalmask,
            )

        return self._normalize_and_remove_none_values(outbound), extra_outbounds

    def _build_hysteria(self, address: str, inbound: SubscriptionInboundData, settings: dict) -> tuple:
        """Build Hysteria outbound - returns (main_outbound, extra_outbounds_list)"""
        return self._build_outbound(
            protocol_type="hysteria",
            address=address,
            inbound=inbound,
            user_settings={"auth": str(settings["auth"])},
        )

    def _build_masque(self, address: str, inbound: SubscriptionInboundData, settings: dict) -> dict:
        """Build MASQUE outbound with user credentials and host/inbound DNS.

        Read credentials from a ``masque`` mapping in ``settings`` when present,
        otherwise from ``settings`` itself; ``pass`` takes precedence over
        ``password``. Return ``(main_outbound, extra_outbounds)``. Invalid
        credentials or DNS values raise ``pydantic.ValidationError``; port
        conversion errors from outbound construction also propagate.
        """
        masque_settings = settings.get("masque")
        if not isinstance(masque_settings, dict):
            masque_settings = settings

        masque_data = MasqueProtocolData.model_validate(
            {
                "user": masque_settings.get("user", ""),
                "password": masque_settings.get("pass", masque_settings.get("password", "")),
                "remote_dns": inbound.masque_remote_dns,
            }
        )

        return self._build_outbound(
            protocol_type="masque",
            address=address,
            inbound=inbound,
            user_settings={
                "user": masque_data.user,
                "pass": masque_data.password,
                "remoteDNS": masque_data.remote_dns,
            },
        )

    def _build_wireguard(self, address: str, inbound: SubscriptionInboundData, settings: dict) -> tuple:
        """Build WireGuard outbound for Xray subscriptions."""
        private_key = settings.get("private_key", "")
        peer_ips = list(settings.get("peer_ips") or [])
        public_key = inbound.wireguard_public_key
        if not private_key or not peer_ips or not public_key:
            return {}

        peer = {
            "endpoint": f"{address}:{self._select_port(inbound.port)}",
            "publicKey": public_key,
            "allowedIPs": inbound.wireguard_allowed_ips or ["0.0.0.0/0", "::/0"],
            "keepAlive": inbound.wireguard_keepalive,
            "preSharedKey": inbound.wireguard_pre_shared_key or None,
        }

        outbound = {
            "protocol": "wireguard",
            "tag": "proxy",
            "settings": {
                "remoteDNS": inbound.wireguard_dns,
                "secretKey": private_key,
                "address": peer_ips,
                "peers": [self._normalize_and_remove_none_values(peer)],
                "mtu": inbound.wireguard_mtu,
                "reserved": self._parse_wireguard_reserved(inbound.wireguard_reserved),
                "domainStrategy": "ForceIP",
            },
        }

        # Handle fragment/noise - create dialer outbound
        extra_outbounds = []
        sockopt = None
        if inbound.fragment_settings or inbound.noise_settings:
            dialer_outbound = self.make_dialer_outbound(inbound.fragment_settings, inbound.noise_settings, "dialer")
            if dialer_outbound:
                extra_outbounds.append(dialer_outbound)
                sockopt = {"dialerProxy": "dialer"}

        # Use streamSettings for sockopt and finalmask
        if sockopt or inbound.finalmask:
            outbound["streamSettings"] = self._stream_setting_config(
                sockopt=sockopt,
                finalmask=inbound.finalmask,
            )

        return self._normalize_and_remove_none_values(outbound), extra_outbounds

    def _build_outbound(
        self,
        protocol_type: str,
        address: str,
        inbound: SubscriptionInboundData,
        user_settings: dict,
    ) -> dict:
        """Return a proxy outbound and a list of optional fragment/noise dialers.

        Apply the inbound's transport, TLS, final mask, and enabled Xray mux
        settings. MASQUE always uses the MASQUE transport, places credentials
        in ``masqueSettings`` and DNS in outbound settings, and omits mux.

        Raises:
            ValueError: A selected port from a comma-separated string is not an integer.
            IndexError: A gRPC multi-mode path beginning with ``/`` lacks the
                ``|`` stream separator.
        """
        network = "masque" if protocol_type == "masque" else inbound.network
        path = inbound.transport_config.path
        vnext_protocols = ("vmess", "vless")
        servers_protocols = ("trojan", "shadowsocks")

        # Process GRPC path
        if network in ("grpc", "gun"):
            if getattr(inbound.transport_config, "multi_mode", False):
                path = self.get_grpc_multi(path)
            else:
                path = self.get_grpc_gun(path)

        if protocol_type in vnext_protocols:
            outbound = {
                "protocol": protocol_type,
                "tag": "proxy",
                "settings": {
                    "vnext": [
                        {
                            "address": address,
                            "port": self._select_port(inbound.port),
                            "users": [
                                user_settings,
                            ],
                        },
                    ]
                },
            }
        elif protocol_type in servers_protocols:
            outbound = {
                "protocol": protocol_type,
                "tag": "proxy",
                "settings": {
                    "servers": [
                        {
                            "address": address,
                            "port": self._select_port(inbound.port),
                            **user_settings,
                        },
                    ]
                },
            }
        elif protocol_type == "hysteria":
            outbound = {
                "protocol": protocol_type,
                "tag": "proxy",
                "settings": {
                    "version": 2,
                    "address": address,
                    "port": self._select_port(inbound.port),
                },
            }
        elif protocol_type == "masque":
            outbound = {
                "protocol": protocol_type,
                "tag": "proxy",
                "settings": {
                    "address": address,
                    "port": self._select_port(inbound.port),
                    "remoteDNS": user_settings.get("remoteDNS"),
                },
            }

        # Build stream settings
        if network == "hysteria":
            auth = ""
            if protocol_type == "hysteria":
                auth = user_settings.get("auth", "")
            elif protocol_type in vnext_protocols:
                auth = user_settings.get("id", "")
            elif protocol_type in servers_protocols:
                auth = user_settings.get("password", "")

            network_setting = {
                "version": 2,
                "auth": auth,
            }

        else:
            network_setting = self._apply_transport(network, inbound, path)
            if protocol_type == "masque" and isinstance(network_setting, dict):
                network_setting.update(
                    {
                        "user": user_settings.get("user"),
                        "pass": user_settings.get("pass"),
                    }
                )

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
            network=None if protocol_type == "masque" else network,
            security=security,
            network_setting=None if protocol_type == "masque" else network_setting,
            tls_settings=tls_settings,
            sockopt=sockopt,
            finalmask=inbound.finalmask,
        )
        if protocol_type == "masque":
            outbound["streamSettings"]["method"] = "masque"
            outbound["streamSettings"]["masqueSettings"] = network_setting

        # Add mux
        if (
            protocol_type != "masque"
            and inbound.mux_settings
            and (xray_mux := inbound.mux_settings.get("xray"))
            and xray_mux.get("enabled")
        ):
            outbound["mux"] = self._normalize_and_remove_none_values(xray_mux)

        return self._normalize_and_remove_none_values(outbound), extra_outbounds

    @staticmethod
    def _stream_setting_config(
        network=None, security=None, network_setting=None, tls_settings=None, sockopt=None, finalmask=None
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

        if finalmask is not None:
            if isinstance(finalmask, BaseModel):
                finalmask = finalmask.model_dump(exclude_none=True, by_alias=True, mode="json")
            try:
                finalmask = FinalMask.model_validate(finalmask)
            except (TypeError, ValueError):
                pass
            if isinstance(finalmask, (FinalMask, dict)):
                stream_settings["finalmask"] = dump_final_mask_for_xray(finalmask)
            else:
                stream_settings["finalmask"] = finalmask

        return stream_settings

    def _select_port(self, port: int | str) -> int:
        """Select a random port if multiple are provided"""
        if isinstance(port, str):
            ports = port.split(",")
            return int(choice(ports))
        return port

    @staticmethod
    def _parse_wireguard_reserved(reserved: str | None) -> list[int] | None:
        """Parse WireGuard reserved bytes from common persisted string formats."""
        if not reserved:
            return None

        raw = reserved.strip()
        if not raw:
            return None

        if raw.startswith("[") and raw.endswith("]"):
            raw = raw[1:-1]

        values: list[int] = []
        for part in raw.split(","):
            piece = part.strip()
            if not piece:
                continue
            try:
                values.append(int(piece))
            except ValueError:
                return None

        return values or None
