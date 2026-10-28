from starlette.types import ASGIApp, Message, Receive, Scope, Send

_MAX_BODY_RESPONSE = b'{"detail":"Request body too large"}'


class RequestBodyTooLarge(Exception):
    """Raised by the wrapped receive channel when a streamed body exceeds the limit."""


class MaxRequestBodySizeMiddleware:
    """
    Reject oversized request bodies before they are buffered in memory.

    Starlette reads a request body fully into memory before running the endpoint, so a single
    unauthenticated POST with a multi-gigabyte payload can exhaust the worker. This middleware
    checks Content-Length up front and also counts streamed chunks for chunked uploads.
    """

    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.max_body_size <= 0:
            await self.app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > self.max_body_size:
            await self._reject(send)
            return

        response_started = False
        received = 0
        limit_hit = False
        rewriting_error = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started, rewriting_error
            if message["type"] == "http.response.start":
                response_started = True
                # FastAPI turns a failure while reading the body into a 400. When that failure
                # was our streamed limit, answer 413 instead so the client sees the real reason.
                if limit_hit and message["status"] == 400:
                    rewriting_error = True
                    message = {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(_MAX_BODY_RESPONSE)).encode("ascii")),
                        ],
                    }
            elif rewriting_error and message["type"] == "http.response.body":
                rewriting_error = False
                message = {"type": "http.response.body", "body": _MAX_BODY_RESPONSE}
            await send(message)

        async def receive_wrapper() -> Message:
            nonlocal received, limit_hit
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_size:
                    limit_hit = True
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except RequestBodyTooLarge:
            if not response_started:
                await self._reject(send)

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return None
        return None

    @staticmethod
    async def _reject(send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_MAX_BODY_RESPONSE)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _MAX_BODY_RESPONSE})
