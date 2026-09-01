import ssl


def test_ssl_context_is_not_globally_replaced():
    """Keep server-side TLS on CPython's native OpenSSL implementation."""
    assert ssl.SSLContext.__module__ == "ssl"
