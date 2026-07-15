from enum import Enum
from ipaddress import ip_network
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models import ProxyHostALPN, ProxyHostFingerprint, ProxyHostSecurity, UserStatus

from .validators import ListValidator, StringArrayValidator


class XHttpModes(str, Enum):
    auto = "auto"
    packet_up = "packet-up"
    stream_up = "stream-up"
    stream_one = "stream-one"


class MultiplexProtocol(str, Enum):
    smux = "smux"
    yamux = "yamux"
    h2mux = "h2mux"


class XUDP(str, Enum):
    reject = "reject"
    allow = "allow"
    skip = "skip"


class ECHQueryStrategy(str, Enum):
    none = "none"
    half = "half"
    full = "full"


class XrayFragmentSettings(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    packets: str = Field(pattern=r"^(:?tlshello|[\d-]{1,16})$")
    length: str = Field(pattern=r"^[\d-]{1,16}$")
    interval: str = Field(pattern=r"^[\d-]{1,16}$", serialization_alias="delay")
    max_split: str | None = Field(default=None, alias="maxSplit")

    @model_validator(mode="before")
    @classmethod
    def delay_to_interval(cls, value):
        if isinstance(value, dict) and "delay" in value:
            value = {**value}
            delay = value.pop("delay")
            value.setdefault("interval", delay)
        return value


class SingBoxFragmentSettings(BaseModel):
    fragment: bool = Field(default=False)
    fragment_fallback_delay: str = Field("", pattern=r"^$|^\d+ms$")
    record_fragment: bool = Field(default=False)


class FragmentSettings(BaseModel):
    xray: XrayFragmentSettings | None = Field(default=None)
    sing_box: SingBoxFragmentSettings | None = Field(default=None)


class XrayNoiseSettings(BaseModel):
    type: str = Field(pattern=r"^$|^(:?rand|array|str|base64|hex)$")
    packet: str | list[int] | None = Field(default=None)
    delay: str | int | None = Field(default=None)
    apply_to: str = Field(default="ip", pattern=r"ip|ipv4|ipv6")
    rand: int | str | None = Field(default=None)
    rand_range: str | None = Field(default=None, alias="randRange", pattern=r"^\d{1,16}(-\d{1,16})?$")

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class NoiseSettings(BaseModel):
    xray: list[XrayNoiseSettings] | None = Field(default=None)


class FinalMaskBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True, use_enum_values=True)


class FinalMaskTcpType(str, Enum):
    header_custom = "header-custom"
    fragment = "fragment"
    sudoku = "sudoku"


class FinalMaskUdpType(str, Enum):
    header_custom = "header-custom"
    header_dns = "header-dns"
    header_dtls = "header-dtls"
    header_srtp = "header-srtp"
    header_utp = "header-utp"
    header_wechat = "header-wechat"
    header_wireguard = "header-wireguard"
    mkcp_original = "mkcp-original"
    mkcp_aes128gcm = "mkcp-aes128gcm"
    noise = "noise"
    salamander = "salamander"
    sudoku = "sudoku"
    xdns = "xdns"
    xicmp = "xicmp"


class FinalMaskQuicCongestion(str, Enum):
    reno = "reno"
    bbr = "bbr"
    brutal = "brutal"
    force_brutal = "force-brutal"


class FinalMaskTcpHeaderCustomSettings(FinalMaskBaseModel):
    clients: list[list[XrayNoiseSettings]] | None = Field(default=None)
    servers: list[list[XrayNoiseSettings]] | None = Field(default=None)
    errors: list[list[XrayNoiseSettings]] | None = Field(default=None)


class FinalMaskUdpHeaderCustomSettings(FinalMaskBaseModel):
    client: list[XrayNoiseSettings] | None = Field(default=None)
    server: list[XrayNoiseSettings] | None = Field(default=None)


class FinalMaskPasswordSettings(FinalMaskBaseModel):
    password: str | None = Field(default=None)


class FinalMaskSudokuSettings(FinalMaskPasswordSettings):
    ascii: str | None = Field(default=None)
    custom_table: str | None = Field(default=None, alias="customTable")
    custom_tables: list[str] | None = Field(default=None, alias="customTables")
    padding_min: int | None = Field(default=None, alias="paddingMin")
    padding_max: int | None = Field(default=None, alias="paddingMax")


class FinalMaskDomainSettings(FinalMaskBaseModel):
    domain: str | None = Field(default=None)


class FinalMaskXicmpSettings(FinalMaskBaseModel):
    listen_ip: str | None = Field(default=None, alias="listenIp")
    id: int | None = Field(default=None)


class FinalMaskNoiseSettings(FinalMaskBaseModel):
    reset: int | None = Field(default=None)
    noise: list[XrayNoiseSettings] | None = Field(default=None)


class FinalMaskUdpHop(FinalMaskBaseModel):
    ports: str | None = Field(default=None)
    interval: str | int | None = Field(default=None)


class FinalMaskQuicParams(FinalMaskBaseModel):
    congestion: FinalMaskQuicCongestion | None = Field(default=None)
    debug: bool | None = Field(default=None)
    brutal_up: str | int | None = Field(default=None, alias="brutalUp")
    brutal_down: str | int | None = Field(default=None, alias="brutalDown")
    udp_hop: FinalMaskUdpHop | None = Field(default=None, alias="udpHop")
    init_stream_receive_window: int | None = Field(default=None, alias="initStreamReceiveWindow")
    max_stream_receive_window: int | None = Field(default=None, alias="maxStreamReceiveWindow")
    init_connection_receive_window: int | None = Field(default=None, alias="initConnectionReceiveWindow")
    max_connection_receive_window: int | None = Field(default=None, alias="maxConnectionReceiveWindow")
    max_idle_timeout: int | None = Field(default=None, alias="maxIdleTimeout")
    keep_alive_period: int | None = Field(default=None, alias="keepAlivePeriod")
    disable_path_mtu_discovery: bool | None = Field(default=None, alias="disablePathMTUDiscovery")
    max_incoming_streams: int | None = Field(default=None, alias="maxIncomingStreams")


FinalMaskTcpSettings = (
    FinalMaskTcpHeaderCustomSettings | XrayFragmentSettings | FinalMaskSudokuSettings | dict[str, Any]
)
FinalMaskUdpSettings = (
    FinalMaskUdpHeaderCustomSettings
    | FinalMaskPasswordSettings
    | FinalMaskSudokuSettings
    | FinalMaskDomainSettings
    | FinalMaskXicmpSettings
    | FinalMaskNoiseSettings
    | dict[str, Any]
)


FINAL_MASK_TCP_SETTINGS_MODELS = {
    FinalMaskTcpType.header_custom: FinalMaskTcpHeaderCustomSettings,
    FinalMaskTcpType.fragment: XrayFragmentSettings,
    FinalMaskTcpType.sudoku: FinalMaskSudokuSettings,
}

FINAL_MASK_UDP_SETTINGS_MODELS = {
    FinalMaskUdpType.header_custom: FinalMaskUdpHeaderCustomSettings,
    FinalMaskUdpType.header_dns: FinalMaskDomainSettings,
    FinalMaskUdpType.header_dtls: FinalMaskPasswordSettings,
    FinalMaskUdpType.header_srtp: FinalMaskPasswordSettings,
    FinalMaskUdpType.header_utp: FinalMaskPasswordSettings,
    FinalMaskUdpType.header_wechat: FinalMaskPasswordSettings,
    FinalMaskUdpType.header_wireguard: FinalMaskPasswordSettings,
    FinalMaskUdpType.mkcp_original: FinalMaskPasswordSettings,
    FinalMaskUdpType.mkcp_aes128gcm: FinalMaskPasswordSettings,
    FinalMaskUdpType.noise: FinalMaskNoiseSettings,
    FinalMaskUdpType.salamander: FinalMaskPasswordSettings,
    FinalMaskUdpType.sudoku: FinalMaskSudokuSettings,
    FinalMaskUdpType.xdns: FinalMaskDomainSettings,
    FinalMaskUdpType.xicmp: FinalMaskXicmpSettings,
}


def _dispatch_final_mask_settings(
    value: Any,
    type_enum: type[Enum],
    settings_models: dict[Enum, type[BaseModel]],
):
    if not isinstance(value, dict):
        return value

    settings = value.get("settings")
    if not isinstance(settings, dict):
        return value

    layer_type = value.get("type")
    if layer_type is None:
        return value

    try:
        layer_type = type_enum(layer_type)
    except ValueError:
        return value

    value = {**value}
    settings_model = settings_models.get(layer_type)
    if settings_model is not None:
        value["settings"] = settings_model.model_validate(settings)
    return value


class FinalMaskTcpLayer(FinalMaskBaseModel):
    type: FinalMaskTcpType
    settings: FinalMaskTcpSettings = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def parse_settings(cls, value):
        return _dispatch_final_mask_settings(value, FinalMaskTcpType, FINAL_MASK_TCP_SETTINGS_MODELS)


class FinalMaskUdpLayer(FinalMaskBaseModel):
    type: FinalMaskUdpType
    settings: FinalMaskUdpSettings = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def parse_settings(cls, value):
        return _dispatch_final_mask_settings(value, FinalMaskUdpType, FINAL_MASK_UDP_SETTINGS_MODELS)


class FinalMask(FinalMaskBaseModel):
    tcp: list[FinalMaskTcpLayer] | None = Field(default=None)
    udp: list[FinalMaskUdpLayer] | None = Field(default=None)
    quic_params: FinalMaskQuicParams | None = Field(default=None, alias="quicParams")


class XMuxSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    max_concurrency: str | None = Field(None, pattern=r"^\d{1,16}(-\d{1,16})?$", alias="maxConcurrency")
    max_connections: str | None = Field(None, pattern=r"^\d{1,16}(-\d{1,16})?$", alias="maxConnections")
    c_max_reuse_times: str | None = Field(None, pattern=r"^\d{1,16}(-\d{1,16})?$", alias="cMaxReuseTimes")
    h_max_reusable_secs: str | None = Field(
        None, pattern=r"^\d{1,16}(-\d{1,16})?$", alias="hMaxReusableSecs"
    )
    h_max_request_times: str | None = Field(
        None, pattern=r"^\d{1,16}(-\d{1,16})?$", alias="hMaxRequestTimes"
    )
    h_keep_alive_period: int | None = Field(None, alias="hKeepAlivePeriod")

    @field_validator(
        "max_concurrency",
        "max_connections",
        "c_max_reuse_times",
        "h_max_reusable_secs",
        "h_max_request_times",
        mode="before",
    )
    @classmethod
    def normalize_numeric_or_range_fields(cls, value):
        if isinstance(value, int):
            return str(value)
        return value


class XHttpSettings(BaseModel):
    mode: XHttpModes | None = Field(default=None)
    no_grpc_header: bool | None = Field(default=None)
    x_padding_bytes: str | None = Field(default=None, pattern=r"^\d{1,16}(-\d{1,16})?$")
    x_padding_obfs_mode: bool | None = Field(default=None)
    x_padding_key: str | None = Field(default=None)
    x_padding_header: str | None = Field(default=None)
    x_padding_placement: str | None = Field(default=None, pattern=r"^$|^(cookie|header|query|queryInHeader)$")
    x_padding_method: str | None = Field(default=None, pattern=r"^$|^(repeat-x|tokenish)$")
    uplink_http_method: str | None = Field(default=None)
    session_placement: str | None = Field(default=None, pattern=r"^$|^(path|cookie|header|query)$")
    session_key: str | None = Field(default=None)
    session_id_table: str | None = Field(default=None, pattern=r"^[\x20-\x7E]*$")
    session_id_length: str | None = Field(default=None, pattern=r"^\d{1,16}(-\d{1,16})?$")
    seq_placement: str | None = Field(default=None, pattern=r"^$|^(path|cookie|header|query)$")
    seq_key: str | None = Field(default=None)
    uplink_data_placement: str | None = Field(default=None, pattern=r"^$|^(body|cookie|header)$")
    uplink_data_key: str | None = Field(default=None)
    uplink_chunk_size: str | None = Field(default=None, pattern=r"^\d{1,16}(-\d{1,16})?$")
    sc_max_each_post_bytes: str | None = Field(default=None, pattern=r"^\d{1,16}(-\d{1,16})?$")
    sc_min_posts_interval_ms: str | None = Field(default=None, pattern=r"^\d{1,16}(-\d{1,16})?$")
    xmux: XMuxSettings | None = Field(default=None)
    download_settings: int | None = Field(default=None)

    @field_validator("mode", mode="before")
    def _empty_mode_to_none(cls, v):
        if v == "":
            return None
        return v

    @field_validator(
        "x_padding_bytes",
        "uplink_chunk_size",
        "sc_max_each_post_bytes",
        "sc_min_posts_interval_ms",
        "session_id_length",
        mode="before",
    )
    @classmethod
    def normalize_numeric_or_range_fields(cls, value):
        if value == "":
            return None
        if isinstance(value, int):
            return str(value)
        return value

    @field_validator(
        "x_padding_key",
        "x_padding_header",
        "x_padding_placement",
        "x_padding_method",
        "uplink_http_method",
        "session_placement",
        "session_key",
        "seq_placement",
        "seq_key",
        "uplink_data_placement",
        "uplink_data_key",
        "uplink_chunk_size",
        mode="before",
    )
    def _empty_str_to_none(cls, v):
        if v == "":
            return None
        return v


class HTTPBase(BaseModel):
    version: str = Field("1.1", pattern=r"^(1(?:\.0|\.1)|2\.0|3\.0)$")
    headers: dict[str, list[str]] | None = Field(default=None)


class HTTPResponse(HTTPBase):
    status: str = Field("200", pattern=r"^[1-5]\d{2}$")
    reason: str = Field(
        "OK",
        pattern=r"^(?i)(?:OK|Created|Accepted|Non-Authoritative Information|No Content|Reset Content|Partial Content|Multiple Choices|Moved Permanently|Found|See Other|Not Modified|Use Proxy|Temporary Redirect|Permanent Redirect|Bad Request|Unauthorized|Payment Required|Forbidden|Not Found|Method Not Allowed|Not Acceptable|Proxy Authentication Required|Request Timeout|Conflict|Gone|Length Required|Precondition Failed|Payload Too Large|URI Too Long|Unsupported Media Type|Range Not Satisfiable|Expectation Failed|I'm a teapot|Misdirected Request|Unprocessable Entity|Locked|Failed Dependency|Too Early|Upgrade Required|Precondition Required|Too Many Requests|Request Header Fields Too Large|Unavailable For Legal Reasons|Internal Server Error|Not Implemented|Bad Gateway|Service Unavailable|Gateway Timeout|HTTP Version Not Supported)$",
    )


class HTTPRequest(HTTPBase):
    method: str = Field("GET", pattern=r"^(GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH|TRACE|CONNECT)$")


class TcpSettings(BaseModel):
    header: str = Field("none", pattern=r"^(?:|none|http)$")
    request: HTTPRequest | None = Field(default=None)
    response: HTTPResponse | None = Field(default=None)


class WebSocketSettings(BaseModel):
    heartbeatPeriod: int | None = Field(default=None)


class KCPSettings(BaseModel):
    mtu: int | None = Field(default=None)
    tti: int | None = Field(default=None)
    uplink_capacity: int | None = Field(default=None)
    downlink_capacity: int | None = Field(default=None)
    congestion: bool | None = Field(default=None)
    read_buffer_size: int | None = Field(default=None)
    write_buffer_size: int | None = Field(default=None)


class GRPCSettings(BaseModel):
    multi_mode: bool = Field(default=False)
    idle_timeout: int | None = Field(default=None)
    health_check_timeout: int | None = Field(default=None)
    permit_without_stream: bool = Field(default=False)
    initial_windows_size: int | None = Field(default=None)


class Brutal(BaseModel):
    enable: bool = Field(default=False)
    up_mbps: int
    down_mbps: int


class SingBoxMuxSettings(BaseModel):
    enable: bool = False
    protocol: MultiplexProtocol = MultiplexProtocol.smux
    max_connections: int | None = Field(default=None)
    max_streams: int | None = Field(default=None)
    min_streams: int | None = Field(default=None)
    padding: bool = False
    brutal: Brutal | None = Field(default=None)


class ClashMuxSettings(SingBoxMuxSettings):
    statistic: bool = False
    only_tcp: bool = False


class XrayMuxSettings(BaseModel):
    enabled: bool = Field(default=False)
    concurrency: int | None = Field(default=None)
    xudp_concurrency: int | None = Field(None, serialization_alias="xudpConcurrency")
    xudp_proxy_udp_443: XUDP = Field(default=XUDP.reject, serialization_alias="xudpProxyUDP443")


class MuxSettings(BaseModel):
    sing_box: SingBoxMuxSettings | None = Field(default=None)
    clash: ClashMuxSettings | None = Field(default=None)
    xray: XrayMuxSettings | None = Field(default=None)


class TransportSettings(BaseModel):
    xhttp_settings: XHttpSettings | None = Field(default=None)
    grpc_settings: GRPCSettings | None = Field(default=None)
    kcp_settings: KCPSettings | None = Field(default=None)
    tcp_settings: TcpSettings | None = Field(default=None)
    websocket_settings: WebSocketSettings | None = Field(default=None)


class FormatVariables(dict):
    def __missing__(self, key):
        return key.join("{}")


class WireGuardHostOverrides(BaseModel):
    """Optional per-host values merged into WireGuard subscription output."""

    allowed_ips: list[str] | None = None
    mtu: int | None = Field(default=None, ge=576, le=9000)
    reserved: str | None = Field(default=None, max_length=64)
    keepalive_seconds: int | None = Field(default=None, ge=0, le=86400)
    dns: list[str] | None = Field(default=None)

    @field_validator("reserved", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v

    @field_validator("allowed_ips", mode="before")
    @classmethod
    def normalize_allowed_ips(cls, value):
        if value in (None, "", []):
            return None
        if not isinstance(value, list):
            raise ValueError("allowed_ips must be a list of CIDR strings")
        normalized: list[str] = []
        for cidr in value:
            if not isinstance(cidr, str) or not cidr.strip():
                continue
            normalized.append(str(ip_network(cidr.strip(), strict=False)))
        return normalized or None


class SubscriptionTemplates(BaseModel):
    xray: int | None = Field(default=None, ge=1)

    @field_validator("xray", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v


class BaseHost(BaseModel):
    id: int | None = Field(default=None)
    remark: str
    address: set[str] = Field(default_factory=set)
    inbound_tag: str | None = Field(default=None)
    port: int | None = Field(default=None)
    sni: set[str] | None = Field(default_factory=set)
    host: set[str] | None = Field(default_factory=set)
    path: str | None = Field(default=None)
    security: ProxyHostSecurity = ProxyHostSecurity.inbound_default
    alpn: list[ProxyHostALPN] | None = Field(default_factory=list)
    fingerprint: ProxyHostFingerprint = ProxyHostFingerprint.none
    allowinsecure: bool | None = Field(default=None)
    is_disabled: bool = Field(default=False)
    http_headers: dict[str, str] | None = Field(default=None)
    transport_settings: TransportSettings | None = Field(default=None)
    mux_settings: MuxSettings | None = Field(default=None)
    fragment_settings: FragmentSettings | None = Field(default=None)
    noise_settings: NoiseSettings | None = Field(default=None)
    random_user_agent: bool = Field(default=False)
    use_sni_as_host: bool = Field(default=False)
    vless_route: str | None = Field(default=None, pattern=r"^$|^[0-9a-fA-F]{4}$")
    priority: int
    status: set[UserStatus] | None = Field(default_factory=set)
    ech_config_list: str | None = Field(default=None)
    ech_query_strategy: ECHQueryStrategy | None = Field(default=None)
    pinned_peer_cert_sha256: str | None = Field(default=None)
    verify_peer_cert_by_name: set[str] | None = Field(default_factory=set)
    wireguard_overrides: WireGuardHostOverrides | None = None
    subscription_templates: SubscriptionTemplates | None = None
    final_mask_settings: FinalMask | None = None

    model_config = ConfigDict(from_attributes=True)

    @property
    def address_str(self) -> str:
        if self.address:
            return ",".join(self.address)
        return ""

    @field_validator("subscription_templates", mode="after")
    @classmethod
    def empty_subscription_templates_to_none(cls, value: SubscriptionTemplates | None):
        if value is not None and value.xray is None:
            return None
        return value


class CreateHost(BaseHost):
    @field_validator("remark", mode="after")
    def validate_remark(cls, v):
        if not v:
            raise ValueError("Remark cannot be empty")
        try:
            v.format_map(FormatVariables())
        except ValueError:
            raise ValueError("Invalid formatting variables")

        return v

    @field_validator("alpn", mode="after")
    def remove_duplicates(cls, v):
        if v:
            return ListValidator.remove_duplicates_preserve_order(v)

    @field_validator("alpn", mode="after")
    def sort_alpn_list(cls, v) -> list:
        priority = {"h3": 0, "h2": 1, "http/1.1": 2}
        if v:
            return sorted(v, key=lambda x: priority[x])

    @field_validator("address", mode="after")
    def validate_address(cls, v):
        return StringArrayValidator.len_check(v, 256)

    @field_validator("sni", "host", mode="after")
    def validate_sets(cls, v: set):
        return StringArrayValidator.len_check(v, 1000)


class BulkHostSelection(BaseModel):
    """Model for bulk host selection by IDs"""

    ids: set[int] = Field(default_factory=set)

    @field_validator("ids", mode="after")
    @classmethod
    def ids_validator(cls, v):
        return ListValidator.not_null_list(list(v), "host")


class RemoveHostsResponse(BaseModel):
    """Response model for bulk host deletion"""

    hosts: list[str]
    count: int


class BulkHostsActionResponse(BaseModel):
    """Response model for bulk host actions."""

    hosts: list[str]
    count: int


class HostListQuery(BaseModel):
    ids: list[int] | None = None
    offset: int = 0
    limit: int = 0
