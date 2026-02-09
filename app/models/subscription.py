"""
Pydantic models for subscription data.
Broken down into small, focused models - each transport/protocol gets only what it needs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, computed_field


class TLSConfig(BaseModel):
    """TLS configuration - only TLS-related fields"""

    tls: str | None = Field(None)
    sni: list[str] | str = Field(default_factory=list)
    fingerprint: str = Field("")
    allowinsecure: bool = Field(False)
    alpn_list: list[str] = Field(default_factory=list)
    ech_config_list: str | None = Field(None)

    # Reality specific
    reality_public_key: str = Field("")
    reality_short_id: str = Field("")
    reality_short_ids: list[str] = Field(default_factory=list)  # List for random selection in share.py
    reality_spx: str = Field("")
    mldsa65_verify: str | None = Field(None)

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

    path: str = Field("")
    host: list[str] | str = Field(default_factory=list)

    model_config = {"validate_assignment": True}


class GRPCTransportConfig(BaseTransportConfig):
    """GRPC/Gun transport - only grpc-specific fields"""

    multi_mode: bool = Field(False, serialization_alias="multiMode")
    idle_timeout: int | None = Field(None)
    health_check_timeout: int | None = Field(None)
    permit_without_stream: bool = Field(False)
    initial_windows_size: int | None = Field(None)
    http_headers: dict[str, str] | None = Field(None)
    random_user_agent: bool = Field(False)


class WebSocketTransportConfig(BaseTransportConfig):
    """WebSocket transport - only ws-specific fields"""

    heartbeat_period: int | None = Field(None, serialization_alias="heartbeatPeriod")
    http_headers: dict[str, str] | None = Field(None)
    random_user_agent: bool = Field(False)


class XHTTPTransportConfig(BaseTransportConfig):
    """xHTTP/SplitHTTP transport - only xhttp-specific fields"""

    mode: str = Field("auto")
    no_grpc_header: bool | None = Field(None)
    sc_max_each_post_bytes: str | int | None = Field(
        None, serialization_alias="scMaxEachPostBytes", pattern=r"^\d{1,16}(?:-\d{1,16})?$"
    )
    sc_min_posts_interval_ms: str | int | None = Field(
        None, serialization_alias="scMinPostsIntervalMs", pattern=r"^\d{1,16}(?:-\d{1,16})?$"
    )
    x_padding_bytes: str | None = Field(None, serialization_alias="xPaddingBytes")
    x_padding_obfs_mode: bool | None = Field(None, serialization_alias="xPaddingObfsMode")
    x_padding_key: str | None = Field(None, serialization_alias="xPaddingKey")
    x_padding_header: str | None = Field(None, serialization_alias="xPaddingHeader")
    x_padding_placement: str | None = Field(None, serialization_alias="xPaddingPlacement")
    x_padding_method: str | None = Field(None, serialization_alias="xPaddingMethod")
    uplink_http_method: str | None = Field(None, serialization_alias="uplinkHTTPMethod")
    session_placement: str | None = Field(None, serialization_alias="sessionPlacement")
    session_key: str | None = Field(None, serialization_alias="sessionKey")
    seq_placement: str | None = Field(None, serialization_alias="seqPlacement")
    seq_key: str | None = Field(None, serialization_alias="seqKey")
    uplink_data_placement: str | None = Field(None, serialization_alias="uplinkDataPlacement")
    uplink_data_key: str | None = Field(None, serialization_alias="uplinkDataKey")
    uplink_chunk_size: int | None = Field(None, serialization_alias="uplinkChunkSize")
    xmux: dict[str, Any] | None = Field(None)
    download_settings: SubscriptionInboundData | dict | None = Field(None, serialization_alias="downloadSettings")
    http_headers: dict[str, str] | None = Field(None)
    random_user_agent: bool = Field(False)


class KCPTransportConfig(BaseTransportConfig):
    """KCP transport - only kcp-specific fields"""

    mtu: int | None = Field(None)
    tti: int | None = Field(None)
    uplink_capacity: int | None = Field(None)
    downlink_capacity: int | None = Field(None)
    congestion: bool = Field(False)
    read_buffer_size: int | None = Field(None)
    write_buffer_size: int | None = Field(None)


class QUICTransportConfig(BaseTransportConfig):
    """QUIC transport - only quic-specific fields"""

    header_type: str = Field("none")


class TCPTransportConfig(BaseTransportConfig):
    """TCP/Raw/HTTP transport - only tcp-specific fields"""

    header_type: str = Field("none")
    request: dict[str, Any] | None = Field(None)
    response: dict[str, Any] | None = Field(None)
    http_headers: dict[str, str] | None = Field(None)
    random_user_agent: bool = Field(False)


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
    encryption: str = Field("none")

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
    is_2022: bool = Field(False)

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
    address: list[str] | str = Field(default_factory=list)
    port: list[int] | int = Field(default_factory=list)
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
    mux_settings: dict[str, Any] | None = Field(None)

    # Shadowsocks specific
    is_2022: bool = Field(False)
    method: str = Field("")
    password: str = Field("")

    # VLESS specific
    encryption: str = Field("none")
    vless_route: str | None = Field(default=None)

    # Flow (from inbound, user can override)
    inbound_flow: str = Field("")
    flow_enabled: bool = Field(False)  # Computed once: if this inbound supports flow

    # Additional settings
    random_user_agent: bool = Field(False)
    use_sni_as_host: bool = Field(False)
    # Fragment and noise settings
    fragment_settings: dict[str, Any] | None = Field(None)
    noise_settings: dict[str, Any] | None = Field(None)
    finalmask: dict[str, Any] | None = Field(None)

    # Priority and status
    priority: int = Field(0)
    status: list[str] | None = Field(None)

    model_config = {"validate_assignment": True}
