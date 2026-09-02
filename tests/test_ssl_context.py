import ssl
from unittest.mock import patch

import pytest

from app.telegram.session import NativeTLSAiohttpSession
from app.utils.http_client import create_outbound_http_session
from app.utils.ssl_context import create_outbound_ssl_context


def test_ssl_context_is_not_globally_replaced():
    """Keep server-side TLS on CPython's native OpenSSL implementation."""
    assert ssl.SSLContext.__module__ == "ssl"


def test_outbound_context_uses_native_ssl_and_trusted_roots():
    """Create a verified native context with a populated CA store."""
    context = create_outbound_ssl_context()

    assert type(context) is ssl.SSLContext
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.cert_store_stats()["x509_ca"] > 0


def test_outbound_context_loads_certifi_bundle():
    """Load the exact CA bundle path supplied by certifi."""
    certifi_bundle = "/controlled/certifi-ca-bundle.pem"
    with (
        patch("app.utils.ssl_context.certifi.where", return_value=certifi_bundle) as certifi_where,
        patch("app.utils.ssl_context.ssl.create_default_context") as create_context,
    ):
        context = create_context.return_value
        result = create_outbound_ssl_context()

    assert result is context
    certifi_where.assert_called_once_with()
    context.load_verify_locations.assert_called_once_with(cafile=certifi_bundle)


@pytest.mark.asyncio
async def test_outbound_http_session_scopes_native_context_to_client():
    """Attach the native context only to the outbound aiohttp connector."""
    session = create_outbound_http_session()
    try:
        context = session.connector._ssl
        assert type(context) is ssl.SSLContext
        assert ssl.SSLContext.__module__ == "ssl"
    finally:
        await session.close()


@pytest.mark.parametrize("proxy", [None, "socks5://127.0.0.1:1080"])
def test_telegram_session_scopes_native_context_to_client(proxy):
    """Attach native TLS to Telegram connectors with and without a proxy."""
    session = NativeTLSAiohttpSession(proxy=proxy)

    context = session._connector_init["ssl"]
    assert type(context) is ssl.SSLContext
    assert ssl.SSLContext.__module__ == "ssl"
