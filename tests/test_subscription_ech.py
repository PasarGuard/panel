from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.clash import ClashMetaConfiguration
from app.subscription.singbox import SingBoxConfiguration

USER_ID = "11111111-1111-1111-1111-111111111111"


def _inbound(tls_config: TLSConfig) -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark="ech",
        inbound_tag="ech-inbound",
        protocol="vless",
        address="edge.example.com",
        port=443,
        network="tcp",
        tls_config=tls_config,
        transport_config=TCPTransportConfig(),
        priority=0,
    )


def test_mihomo_ech_supports_dns_queries_without_a_static_config():
    tls_config = TLSConfig(
        tls="tls",
        sni="public.example.com",
        ech_config_list="xray-only-value",
        mihomo_ech_query_server_name="ech.example.com",
    )
    configuration = ClashMetaConfiguration()

    configuration.add("mihomo ech", "edge.example.com", _inbound(tls_config), {"id": USER_ID})

    assert configuration.data["proxies"][0]["ech-opts"] == {
        "enable": True,
        "query-server-name": "ech.example.com",
    }


def test_mihomo_ech_emits_static_config_and_query_server_name():
    tls_config = TLSConfig(
        tls="tls",
        mihomo_ech_config="mihomo-base64-config",
        mihomo_ech_query_server_name="ech.example.com",
    )
    configuration = ClashMetaConfiguration()

    configuration.add("mihomo ech", "edge.example.com", _inbound(tls_config), {"id": USER_ID})

    assert configuration.data["proxies"][0]["ech-opts"] == {
        "enable": True,
        "config": "mihomo-base64-config",
        "query-server-name": "ech.example.com",
    }


def test_mihomo_download_settings_include_format_specific_ech():
    tls_config = TLSConfig(
        tls="tls",
        mihomo_ech_query_server_name="download-ech.example.com",
    )
    configuration = ClashMetaConfiguration()
    download_settings = {}

    configuration._apply_mihomo_download_tls(download_settings, tls_config)

    assert download_settings["ech-opts"] == {
        "enable": True,
        "query-server-name": "download-ech.example.com",
    }


def test_sing_box_ech_supports_dns_queries_without_a_static_config():
    tls_config = TLSConfig(
        tls="tls",
        sni="public.example.com",
        ech_config_list="xray-only-value",
        sing_box_ech_query_server_name="ech.example.com",
    )
    configuration = SingBoxConfiguration()

    configuration.add("sing-box ech", "edge.example.com", _inbound(tls_config), {"id": USER_ID})

    assert configuration.config["outbounds"][0]["tls"]["ech"] == {
        "enabled": True,
        "query_server_name": "ech.example.com",
    }


def test_sing_box_ech_wraps_base64_config_as_pem_lines():
    tls_config = TLSConfig(
        tls="tls",
        sing_box_ech_config="sing-box-base64-config",
        sing_box_ech_query_server_name="ech.example.com",
    )
    configuration = SingBoxConfiguration()

    configuration.add("sing-box ech", "edge.example.com", _inbound(tls_config), {"id": USER_ID})

    assert configuration.config["outbounds"][0]["tls"]["ech"] == {
        "enabled": True,
        "config": [
            "-----BEGIN ECH CONFIGS-----",
            "sing-box-base64-config",
            "-----END ECH CONFIGS-----",
        ],
        "query_server_name": "ech.example.com",
    }
