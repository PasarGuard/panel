from aiogram.client.session.aiohttp import AiohttpSession

from app.utils.ssl_context import create_outbound_ssl_context


class NativeTLSAiohttpSession(AiohttpSession):
    """Use native OpenSSL with system and certifi roots for Telegram HTTPS."""

    def __init__(self, proxy=None, limit: int = 100, **kwargs):
        super().__init__(proxy=proxy, limit=limit, **kwargs)
        # aiogram has no public SSLContext argument. It builds its connector
        # from this mapping for both direct and proxied sessions.
        self._connector_init["ssl"] = create_outbound_ssl_context()
