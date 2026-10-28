from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware, IdentityResponder
from starlette.types import Receive, Scope, Send


def accepts_gzip(accept_encoding: str) -> bool:
    for item in accept_encoding.split(","):
        coding, _, params = item.partition(";")
        if coding.strip().lower() != "gzip":
            continue
        for param in params.split(";"):
            name, _, value = param.partition("=")
            if name.strip().lower() == "q":
                try:
                    return float(value) > 0
                except ValueError:
                    return False
        return True
    return False


class PanelGZipMiddleware(GZipMiddleware):
    """Starlette's gzip, but honors `gzip;q=0` and leaves range responses alone.

    Starlette only checks for the substring "gzip", and gzipping a 206 body breaks its Content-Range offsets.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = Headers(scope=scope)
            if "range" in headers or not accepts_gzip(headers.get("accept-encoding", "")):
                await IdentityResponder(self.app, self.minimum_size)(scope, receive, send)
                return
        await super().__call__(scope, receive, send)
