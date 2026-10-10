from app.core.xray import XRayConfig
from app.models.host import XHttpSettings, XMuxSettings
from app.models.subscription import SubscriptionInboundData, TLSConfig, XHTTPTransportConfig
from app.subscription.clash import ClashConfiguration, ClashMetaConfiguration
from app.subscription.xray import XrayConfiguration

USER_ID = "11111111-1111-1111-1111-111111111111"


def _xhttp_inbound(
    *,
    protocol: str = "vless",
    transport_config: XHTTPTransportConfig | None = None,
    tls_config: TLSConfig | None = None,
    address: str = "edge.example.com",
    port: int = 443,
) -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark="xhttp",
        inbound_tag="xhttp-inbound",
        protocol=protocol,
        address=address,
        port=port,
        network="xhttp",
        tls_config=tls_config or TLSConfig(tls="tls", sni="sni.example.com", fingerprint="chrome"),
        transport_config=transport_config or XHTTPTransportConfig(path="/up", host="cdn.example.com", mode="stream-up"),
        priority=0,
    )


def test_classic_clash_skips_xhttp_but_clash_meta_generates_it():
    classic = ClashConfiguration()
    classic.add(
        "classic xhttp",
        "edge.example.com",
        _xhttp_inbound(protocol="vmess"),
        {"id": USER_ID},
    )

    meta = ClashMetaConfiguration()
    meta.add("meta xhttp", "edge.example.com", _xhttp_inbound(), {"id": USER_ID})

    assert classic.data["proxies"] == []
    assert len(meta.data["proxies"]) == 1
    assert meta.data["proxies"][0]["network"] == "xhttp"
    assert meta.data["proxies"][0]["xhttp-opts"]["path"] == "/up"


def test_clash_meta_skips_non_vless_xhttp():
    meta = ClashMetaConfiguration()

    meta.add(
        "meta vmess xhttp",
        "edge.example.com",
        _xhttp_inbound(protocol="vmess"),
        {"id": USER_ID},
    )

    assert meta.data["proxies"] == []


def test_clash_meta_xhttp_opts_include_advanced_fields_and_download_settings():
    download_settings = _xhttp_inbound(
        transport_config=XHTTPTransportConfig(
            path="/down",
            host="download-host.example.com",
            http_headers={"Host": "ignored.example.com", "X-Down": "1"},
            xmux={"maxConcurrency": "4-8", "hKeepAlivePeriod": 0},
        ),
        tls_config=TLSConfig(
            tls="tls",
            sni="download-sni.example.com",
            fingerprint="chrome",
            allowinsecure=False,
            alpn_list=["h2"],
        ),
        address="download.example.com",
        port=8443,
    )
    transport_config = XHTTPTransportConfig(
        path="/up",
        host="cdn.example.com",
        mode="packet-up",
        no_grpc_header=False,
        sc_max_each_post_bytes="1000000",
        sc_min_posts_interval_ms="30",
        x_padding_bytes="100-1000",
        x_padding_obfs_mode=False,
        x_padding_key="x_padding",
        x_padding_header="Referer",
        x_padding_placement="queryInHeader",
        x_padding_method="tokenish",
        uplink_http_method="PATCH",
        session_placement="query",
        session_key="sid",
        seq_placement="header",
        seq_key="seq",
        uplink_data_placement="cookie",
        uplink_data_key="data",
        uplink_chunk_size="3072",
        xmux={"maxConcurrency": "16-32", "c_max_reuse_times": "2", "hKeepAlivePeriod": 0},
        download_settings=download_settings,
        http_headers={"Host": "ignored.example.com", "X-Test": "1", "X-Forwarded-For": ""},
    )

    meta = ClashMetaConfiguration()
    meta.add("meta xhttp", "edge.example.com", _xhttp_inbound(transport_config=transport_config), {"id": USER_ID})

    opts = meta.data["proxies"][0]["xhttp-opts"]
    assert opts["headers"] == {"X-Test": "1", "X-Forwarded-For": ""}
    assert opts["no-grpc-header"] is False
    assert opts["x-padding-obfs-mode"] is False
    assert opts["x-padding-key"] == "x_padding"
    assert opts["x-padding-header"] == "Referer"
    assert opts["x-padding-placement"] == "queryInHeader"
    assert opts["x-padding-method"] == "tokenish"
    assert opts["uplink-http-method"] == "PATCH"
    assert opts["session-placement"] == "query"
    assert opts["session-key"] == "sid"
    assert opts["seq-placement"] == "header"
    assert opts["seq-key"] == "seq"
    assert opts["uplink-data-placement"] == "cookie"
    assert opts["uplink-data-key"] == "data"
    assert opts["uplink-chunk-size"] == "3072"
    assert opts["sc-max-each-post-bytes"] == "1000000"
    assert opts["sc-min-posts-interval-ms"] == "30"
    assert opts["reuse-settings"] == {
        "max-concurrency": "16-32",
        "c-max-reuse-times": "2",
        "h-keep-alive-period": 0,
    }

    download_opts = opts["download-settings"]
    assert download_opts["server"] == "download.example.com"
    assert download_opts["port"] == 8443
    assert download_opts["path"] == "/down"
    assert download_opts["host"] == "download-host.example.com"
    assert download_opts["headers"] == {"X-Down": "1"}
    assert download_opts["reuse-settings"] == {"max-concurrency": "4-8", "h-keep-alive-period": 0}
    assert download_opts["tls"] is True
    assert download_opts["servername"] == "download-sni.example.com"
    assert download_opts["skip-cert-verify"] is False
    assert download_opts["client-fingerprint"] == "chrome"
    assert download_opts["alpn"] == ["h2"]


def test_clash_meta_xhttp_serializes_raw_xray_download_settings_dict_safely():
    transport_config = XHTTPTransportConfig(
        path="/up",
        host="cdn.example.com",
        download_settings={
            "address": "download.example.com",
            "port": 8443,
            "streamSettings": {
                "network": "xhttp",
                "security": "tls",
                "tlsSettings": {
                    "serverName": "download-sni.example.com",
                    "fingerprint": "chrome",
                    "allowInsecure": False,
                    "alpn": ["h2"],
                },
                "xhttpSettings": {
                    "path": "/raw-down",
                    "host": "download-host.example.com",
                    "extra": {
                        "headers": {"Host": "ignored.example.com", "X-Raw": "1", "X-Empty": ""},
                        "xmux": {"maxConcurrency": "2-4"},
                    },
                },
            },
        },
    )

    meta = ClashMetaConfiguration()
    meta.add("meta xhttp", "edge.example.com", _xhttp_inbound(transport_config=transport_config), {"id": USER_ID})

    download_opts = meta.data["proxies"][0]["xhttp-opts"]["download-settings"]
    assert "address" not in download_opts
    assert "streamSettings" not in download_opts
    assert download_opts == {
        "path": "/raw-down",
        "host": "download-host.example.com",
        "headers": {"X-Raw": "1", "X-Empty": ""},
        "reuse-settings": {"max-concurrency": "2-4"},
        "server": "download.example.com",
        "port": 8443,
        "tls": True,
        "alpn": ["h2"],
        "skip-cert-verify": False,
        "servername": "download-sni.example.com",
        "client-fingerprint": "chrome",
    }


def test_xray_parser_reads_xhttp_extra_advanced_fields():
    parsed = XRayConfig(
        {
            "inbounds": [
                {
                    "tag": "vless-xhttp",
                    "port": 443,
                    "protocol": "vless",
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {
                        "network": "xhttp",
                        "xhttpSettings": {
                            "path": "/up",
                            "host": "cdn.example.com",
                            "mode": "packet-up",
                            "extra": {
                                "headers": {"X-Test": "1"},
                                "noGRPCHeader": True,
                                "scMaxEachPostBytes": "1000000",
                                "scMinPostsIntervalMs": "30",
                                "xPaddingObfsMode": True,
                                "uplinkHTTPMethod": "PATCH",
                                "sessionPlacement": "query",
                                "sessionKey": "sid",
                                "seqPlacement": "header",
                                "seqKey": "seq",
                                "uplinkDataPlacement": "cookie",
                                "uplinkDataKey": "data",
                                "uplinkChunkSize": "3072",
                                "xmux": {"maxConcurrency": "16-32", "hKeepAlivePeriod": 0},
                                "downloadSettings": {"address": "download.example.com"},
                            },
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        }
    )

    inbound = parsed.inbounds_by_tag["vless-xhttp"]
    assert inbound["http_headers"] == {"X-Test": "1"}
    assert inbound["no_grpc_header"] is True
    assert inbound["sc_max_each_post_bytes"] == "1000000"
    assert inbound["sc_min_posts_interval_ms"] == "30"
    assert inbound["x_padding_obfs_mode"] is True
    assert inbound["uplink_http_method"] == "PATCH"
    assert inbound["session_placement"] == "query"
    assert inbound["session_key"] == "sid"
    assert inbound["seq_placement"] == "header"
    assert inbound["seq_key"] == "seq"
    assert inbound["uplink_data_placement"] == "cookie"
    assert inbound["uplink_data_key"] == "data"
    assert inbound["uplink_chunk_size"] == "3072"
    assert inbound["xmux"] == {"maxConcurrency": "16-32", "hKeepAlivePeriod": 0}
    assert inbound["download_settings"] == {"address": "download.example.com"}


def test_xhttp_models_accept_integer_numeric_range_fields_as_strings():
    transport = XHTTPTransportConfig(
        sc_max_each_post_bytes=4096,
        sc_min_posts_interval_ms=30,
        x_padding_bytes=128,
        uplink_chunk_size=2048,
    )

    assert transport.sc_max_each_post_bytes == "4096"
    assert transport.sc_min_posts_interval_ms == "30"
    assert transport.x_padding_bytes == "128"
    assert transport.uplink_chunk_size == "2048"

    host_settings = XHttpSettings(
        sc_max_each_post_bytes=4096,
        sc_min_posts_interval_ms=30,
        x_padding_bytes=128,
        uplink_chunk_size=2048,
        xmux=XMuxSettings(max_concurrency=4, max_connections=8),
    )

    assert host_settings.sc_max_each_post_bytes == "4096"
    assert host_settings.sc_min_posts_interval_ms == "30"
    assert host_settings.x_padding_bytes == "128"
    assert host_settings.uplink_chunk_size == "2048"
    assert host_settings.xmux.max_concurrency == "4"
    assert host_settings.xmux.max_connections == "8"


def test_xray_parser_does_not_mix_top_level_advanced_fields_when_extra_exists():
    parsed = XRayConfig(
        {
            "inbounds": [
                {
                    "tag": "vless-xhttp",
                    "port": 443,
                    "protocol": "vless",
                    "settings": {"clients": [], "decryption": "none"},
                    "streamSettings": {
                        "network": "xhttp",
                        "xhttpSettings": {
                            "path": "/up",
                            "host": "cdn.example.com",
                            "mode": "packet-up",
                            "xPaddingObfsMode": True,
                            "uplinkHTTPMethod": "PATCH",
                            "extra": {"sessionKey": "sid"},
                        },
                    },
                }
            ],
            "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        }
    )

    inbound = parsed.inbounds_by_tag["vless-xhttp"]
    assert inbound["session_key"] == "sid"
    assert inbound["x_padding_obfs_mode"] is None
    assert inbound["uplink_http_method"] is None


def test_xray_xhttp_always_uses_session_id_keys():
    conf = XrayConfiguration()
    cfg = XHTTPTransportConfig(
        path="/up",
        host="cdn.example.com",
        mode="stream-up",
        session_placement="query",
        session_key="sid",
        session_id_table="Base62",
        session_id_length="8-16",
    )

    extra = conf._transport_xhttp(cfg, "/up")["extra"]

    assert extra["sessionIDPlacement"] == "query"
    assert extra["sessionIDKey"] == "sid"
    assert extra["sessionIDTable"] == "Base62"
    assert extra["sessionIDLength"] == "8-16"
    assert "sessionPlacement" not in extra
    assert "sessionKey" not in extra
