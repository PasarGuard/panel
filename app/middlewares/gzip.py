from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.gzip import GZipMiddleware, GZipResponder, IdentityResponder
from starlette.types import Message, Receive, Scope, Send


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
    """Starlette's gzip with a proper Accept-Encoding parse, no range compression and weak ETags.

    Starlette only checks for the lowercase substring "gzip", and gzipping a 206 body breaks its Content-Range
    offsets. A gzipped body keeps the file's strong ETag, so a client could resume it with If-Range and get
    identity bytes; making it weak (like nginx) makes If-Range fall back to a full response.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if "range" in headers or not accepts_gzip(headers.get("accept-encoding", "")):
            await IdentityResponder(self.app, self.minimum_size)(scope, receive, send)
            return

        async def send_with_weak_etag(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(raw=message["headers"])
                etag = response_headers.get("etag")
                if etag and not etag.startswith("W/") and response_headers.get("content-encoding") == "gzip":
                    response_headers["etag"] = f"W/{etag}"
            await send(message)

        responder = GZipResponder(self.app, self.minimum_size, compresslevel=self.compresslevel)
        await responder(scope, receive, send_with_weak_etag)
