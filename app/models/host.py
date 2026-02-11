from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class XrayFragmentSettings(BaseModel):
    packets: str = Field(pattern=r"^(:?tlshello|[\d-]{1,16})$")
    length: str = Field(pattern=r"^[\d-]{1,16}$")
    interval: str = Field(pattern=r"^[\d-]{1,16}$")


class SingBoxFragmentSettings(BaseModel):
    fragment: bool = Field(default=False)
    fragment_fallback_delay: str = Field("", pattern=r"^$|^\d+ms$")
    record_fragment: bool = Field(default=False)


class FragmentSettings(BaseModel):
    xray: XrayFragmentSettings | None = Field(default=None)
    sing_box: SingBoxFragmentSettings | None = Field(default=None)


class XrayNoiseSettings(BaseModel):
    type: str = Field(pattern=r"^(:?rand|str|base64|hex)$")
    packet: str
    delay: str = Field(pattern=r"^\d{1,16}(-\d{1,16})?$")
    apply_to: str = Field(default="ip", pattern=r"ip|ipv4|ipv6")


class NoiseSettings(BaseModel):
    xray: list[XrayNoiseSettings] | None = Field(default=None)


class XMuxSettings(BaseModel):
    max_concurrency: str | int | None = Field(
        None, pattern=r"^\d{1,16}(-\d{1,16})?$", serialization_alias="maxConcurrency"
    )
    max_connections: str | int | None = Field(
        None, pattern=r"^\d{1,16}(-\d{1,16})?$", serialization_alias="maxConnections"
    )
    c_max_reuse_times: str | int | None = Field(
        None, pattern=r"^\d{1,16}(-\d{1,16})?$", serialization_alias="cMaxReuseTimes"
    )
    h_max_reusable_secs: str | int | None = Field(
        None, pattern=r"^\d{1,16}(-\d{1,16})?$", serialization_alias="hMaxReusableSecs"
    )
    h_max_request_times: str | int | None = Field(
        None, pattern=r"^\d{1,16}(-\d{1,16})?$", serialization_alias="hMaxRequestTimes"
    )
    h_keep_alive_period: int | None = Field(None, serialization_alias="hKeepAlivePeriod")


class XHttpSettings(BaseModel):
    mode: XHttpModes | None = Field(default=None)
    no_grpc_header: bool | None = Field(default=None)
    x_padding_bytes: str | int | None = Field(default=None, pattern=r"^\d{1,16}(-\d{1,16})?$")
    x_padding_obfs_mode: bool | None = Field(default=None)
    x_padding_key: str | None = Field(default=None)
    x_padding_header: str | None = Field(default=None)
    x_padding_placement: str | None = Field(default=None, pattern=r"^$|^(cookie|header|query|queryInHeader)$")
    x_padding_method: str | None = Field(default=None, pattern=r"^$|^(repeat-x|tokenish)$")
    uplink_http_method: str | None = Field(default=None)
    session_placement: str | None = Field(default=None, pattern=r"^$|^(path|cookie|header|query)$")
    session_key: str | None = Field(default=None)
    seq_placement: str | None = Field(default=None, pattern=r"^$|^(path|cookie|header|query)$")
    seq_key: str | None = Field(default=None)
    uplink_data_placement: str | None = Field(default=None, pattern=r"^$|^(body|cookie|header)$")
    uplink_data_key: str | None = Field(default=None)
    uplink_chunk_size: int | None = Field(default=None)
    sc_max_each_post_bytes: str | int | None = Field(default=None, pattern=r"^\d{1,16}(-\d{1,16})?$")
    sc_min_posts_interval_ms: str | int | None = Field(default=None, pattern=r"^\d{1,16}(-\d{1,16})?$")
    xmux: XMuxSettings | None = Field(default=None)
    download_settings: int | None = Field(default=None)

    @field_validator("mode", mode="before")
    def _empty_mode_to_none(cls, v):
        if v == "":
            return None
        return v

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
    pinnedPeerCertSha256:str| None = Field(default=None)

    model_config = ConfigDict(from_attributes=True)

    @property
    def address_str(self) -> str:
        if self.address:
            return ",".join(self.address)
        return ""


class HostSimple(BaseModel):
    """Lightweight host model for list dropdowns."""

    id: int
    remark: str
    address: set[str]
    port: int | None = None
    inbound_tag: str | None = None
    priority: int
    model_config = ConfigDict(from_attributes=True)


class HostsSimpleResponse(BaseModel):
    """Response model for lightweight host list."""

    hosts: list[HostSimple]
    total: int


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
