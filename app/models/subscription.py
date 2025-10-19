"""
Pydantic models for subscription data.
Broken down into small, focused models - each transport/protocol gets only what it needs.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field


class ClientType(str, Enum):
    """Supported subscription client types"""

    XRAY = "xray"
    SINGBOX = "sing-box"
    CLASH = "clash"
    CLASH_META = "clash-meta"
    LINKS = "links"
    OUTLINE = "outline"


# ========== TLS Configuration (Shared) ==========


class TLSConfig(BaseModel):
    """TLS configuration - only TLS-related fields"""

    tls: str | None = None
    sni: list[str] | str = Field(default_factory=list)
    fingerprint: str = ""
    allowinsecure: bool = False
    alpn_list: list[str] = Field(default_factory=list)
    ech_config_list: str | None = None
    fragment_settings: dict[str, Any] | None = None
    noise_settings: dict[str, Any] | None = None

    # Reality specific
    reality_public_key: str = ""
    reality_short_id: str = ""
    reality_short_ids: list[str] = Field(default_factory=list)  # List for random selection in share.py
    reality_spx: str = ""
    mldsa65_verify: str | None = None

    @computed_field
    @property
    def alpn_singbox(self) -> list[str] | None:
        """ALPN formatted for sing-box (list)"""
        return self.alpn_list if self.alpn_list else None

    @computed_field
    @property
    def alpn_links(self) -> str | None:
        """ALPN formatted for links (comma-separated string)"""
        return ",".join(self.alpn_list) if self.alpn_list else None

    @computed_field
    @property
    def fp(self) -> str:
        """Alias for fingerprint"""
        return self.fingerprint

    @computed_field
    @property
    def ais(self) -> bool:
        """Alias for allowinsecure"""
        return self.allowinsecure

    model_config = {"validate_assignment": True}


# ========== Transport-Specific Models (Only relevant fields) ==========


class BaseTransportConfig(BaseModel):
    """Base config for all transports - minimal shared fields"""

    path: str = ""
    host: list[str] | str = Field(default_factory=list)

    model_config = {"validate_assignment": True}


class GRPCTransportConfig(BaseTransportConfig):
    """GRPC/Gun transport - only grpc-specific fields"""

    multi_mode: bool = False
    idle_timeout: int | None = None
    health_check_timeout: int | None = None
    permit_without_stream: bool = False
    initial_windows_size: int | None = None
    http_headers: dict[str, str] | None = None
    random_user_agent: bool = False


class WebSocketTransportConfig(BaseTransportConfig):
    """WebSocket transport - only ws-specific fields"""

    heartbeat_period: int | None = None
    http_headers: dict[str, str] | None = None
    random_user_agent: bool = False


class XHTTPTransportConfig(BaseTransportConfig):
    """xHTTP/SplitHTTP transport - only xhttp-specific fields"""

    mode: str = "auto"
    no_grpc_header: bool | None = None
    sc_max_each_post_bytes: int | None = None
    sc_min_posts_interval_ms: int | None = None
    x_padding_bytes: str | None = None
    xmux: dict[str, Any] | None = None
    download_settings: dict[str, Any] | None = None
    http_headers: dict[str, str] | None = None
    random_user_agent: bool = False


class KCPTransportConfig(BaseTransportConfig):
    """KCP transport - only kcp-specific fields"""

    header_type: str = "none"
    mtu: int | None = None
    tti: int | None = None
    uplink_capacity: int | None = None
    downlink_capacity: int | None = None
    congestion: bool = False
    read_buffer_size: int | None = None
    write_buffer_size: int | None = None


class QUICTransportConfig(BaseTransportConfig):
    """QUIC transport - only quic-specific fields"""

    header_type: str = "none"


class TCPTransportConfig(BaseTransportConfig):
    """TCP/Raw/HTTP transport - only tcp-specific fields"""

    header_type: str = "none"
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    http_headers: dict[str, str] | None = None
    random_user_agent: bool = False


# ========== Protocol-Specific Models (Only protocol fields) ==========


class VMESSProtocolData(BaseModel):
    """VMess protocol - only vmess-specific fields"""

    id: str
    port: int | str
    address: str
    remark: str

    model_config = {"validate_assignment": True}


class VLESSProtocolData(BaseModel):
    """VLESS protocol - only vless-specific fields"""

    id: str
    port: int | str
    address: str
    remark: str
    encryption: str = "none"

    model_config = {"validate_assignment": True}


class TrojanProtocolData(BaseModel):
    """Trojan protocol - only trojan-specific fields"""

    password: str
    port: int | str
    address: str
    remark: str

    model_config = {"validate_assignment": True}


class ShadowsocksProtocolData(BaseModel):
    """Shadowsocks protocol - only ss-specific fields"""

    method: str
    password: str
    port: int | str
    address: str
    remark: str
    is_2022: bool = False

    model_config = {"validate_assignment": True}


# ========== Legacy Full Model (For backward compatibility during migration) ==========


class SubscriptionInboundData(BaseModel):
    """
    Optimized inbound data - stores small config instances directly.
    No more creating instances on every method call!
    """

    # Basic info
    remark: str
    inbound_tag: str
    protocol: str
    address: list[str]
    port: list[int]  # List of ports for random selection in share.py
    network: str

    # Store small config instances directly (created once!)
    tls_config: TLSConfig
    transport_config: (
        GRPCTransportConfig
        | WebSocketTransportConfig
        | XHTTPTransportConfig
        | KCPTransportConfig
        | QUICTransportConfig
        | TCPTransportConfig
    )

    # Mux settings
    mux_settings: dict[str, Any] | None = None

    # Shadowsocks specific
    is_2022: bool = False
    method: str = ""
    password: str = ""

    # VLESS specific
    encryption: str = "none"

    # Flow (from inbound, user can override)
    inbound_flow: str = ""

    # Additional settings
    random_user_agent: bool = False
    use_sni_as_host: bool = False

    # Priority and status
    priority: int = 0
    status: list[str] | None = None

    model_config = {"validate_assignment": True}
