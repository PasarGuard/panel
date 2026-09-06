import aiohttp

from app.utils.ssl_context import create_outbound_ssl_context


def create_outbound_http_session(*, proxy: str | None = None, timeout_seconds: float = 10) -> aiohttp.ClientSession:
    """Create an HTTP client whose TLS changes cannot affect server sockets."""
    return aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=create_outbound_ssl_context()),
        timeout=aiohttp.ClientTimeout(total=timeout_seconds),
        proxy=proxy,
    )
