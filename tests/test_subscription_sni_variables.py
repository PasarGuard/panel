import pytest

from app.models.subscription import SubscriptionInboundData, TCPTransportConfig, TLSConfig
from app.subscription.share import process_host


def _inbound(*, sni: list[str], use_sni_as_host: bool = False) -> SubscriptionInboundData:
    return SubscriptionInboundData(
        remark="vless",
        inbound_tag="vless-inbound",
        protocol="vless",
        address=["edge.example.com"],
        port=[443],
        network="tcp",
        tls_config=TLSConfig(tls="tls", sni=sni),
        transport_config=TCPTransportConfig(host=["host.example.com"]),
        use_sni_as_host=use_sni_as_host,
        priority=0,
    )


@pytest.mark.asyncio
async def test_process_host_formats_sni_variables():
    result = await process_host(
        _inbound(sni=["{USERNAME}.example.com"]),
        {"USERNAME": "alice"},
        ["vless-inbound"],
        {"vless": {"id": "11111111-1111-1111-1111-111111111111"}},
    )

    assert result is not None
    inbound, _ = result
    assert inbound.tls_config.sni == "alice.example.com"


@pytest.mark.asyncio
async def test_process_host_use_sni_as_host_uses_formatted_sni():
    result = await process_host(
        _inbound(sni=["{USERNAME}.example.com"], use_sni_as_host=True),
        {"USERNAME": "bob"},
        ["vless-inbound"],
        {"vless": {"id": "11111111-1111-1111-1111-111111111111"}},
    )

    assert result is not None
    inbound, _ = result
    assert inbound.tls_config.sni == "bob.example.com"
    assert inbound.transport_config.host == "bob.example.com"
