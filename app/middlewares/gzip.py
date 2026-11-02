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
    identity bytes; making it weak (like nginx) marks the gzipped copy. Only a strong If-Range (an identity
    copy) gets a range; a date or weak If-Range may come from a gzipped copy, so it gets the full body.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if not accepts_gzip(headers.get("accept-encoding", "")):
            await IdentityResponder(self.app, self.minimum_size)(scope, receive, send)
            return
        if "range" in headers:
            if_range = headers.get("if-range")
            if if_range is None or if_range.startswith('"'):
                await IdentityResponder(self.app, self.minimum_size)(scope, receive, send)
                return
            scope = {**scope, "headers": [(k, v) for k, v in scope["headers"] if k not in (b"range", b"if-range")]}
        if_none_match = headers.get("if-none-match", "")

        responder = GZipResponder(self.app, self.minimum_size, compresslevel=self.compresslevel)

        async def send_with_weak_etag(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(raw=message["headers"])
                etag = response_headers.get("etag")
                if etag and not etag.startswith("W/"):
                    # content_encoding_set: the app sent its own encoding, so the body and its ETag are untouched.
                    if response_headers.get("content-encoding") == "gzip" and not responder.content_encoding_set:
                        response_headers["etag"] = f"W/{etag}"
                    elif message["status"] == 304 and f"W/{etag}" in if_none_match:
                        # The client revalidated its gzipped copy: answer with that copy's validators.
                        response_headers["etag"] = f"W/{etag}"
                        response_headers.add_vary_header("Accept-Encoding")
            await send(message)

        await responder(scope, receive, send_with_weak_etag)
