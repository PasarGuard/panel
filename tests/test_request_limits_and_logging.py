import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import middlewares
from app.middlewares.request_limits import MaxRequestBodySizeMiddleware
from app.middlewares.request_logging import redact_log_path


class _EchoApp:
    def __init__(self) -> None:
        self.body = b""
        self.started = False

    async def __call__(self, scope, receive, send) -> None:
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            self.body += message.get("body", b"")
            if not message.get("more_body"):
                break
        self.started = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {"type": "http", "method": "POST", "path": "/", "headers": headers or []}


@pytest.mark.asyncio
async def test_body_limit_rejects_oversized_content_length_before_endpoint_runs():
    app = _EchoApp()
    middleware = MaxRequestBodySizeMiddleware(app, max_body_size=1024)
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"x" * 4096, "more_body": False}

    async def send(message):
        sent.append(message)

    await middleware(_scope([(b"content-length", b"4096")]), receive, send)

    assert app.started is False
    assert app.body == b""
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_body_limit_rejects_streamed_overflow_without_content_length():
    app = _EchoApp()
    middleware = MaxRequestBodySizeMiddleware(app, max_body_size=8)
    sent: list[dict] = []
    chunks = [
        {"type": "http.request", "body": b"12345", "more_body": True},
        {"type": "http.request", "body": b"67890", "more_body": True},
        {"type": "http.request", "body": b"", "more_body": False},
    ]

    async def receive():
        return chunks.pop(0)

    async def send(message):
        sent.append(message)

    await middleware(_scope(), receive, send)

    assert app.started is False
    assert any(message["type"] == "http.response.start" and message["status"] == 413 for message in sent)


@pytest.mark.asyncio
async def test_body_limit_allows_small_request():
    app = _EchoApp()
    middleware = MaxRequestBodySizeMiddleware(app, max_body_size=1024)
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(message):
        sent.append(message)

    await middleware(_scope([(b"content-length", b"2")]), receive, send)

    assert app.started is True
    assert sent[0]["status"] == 200


class _FastApiLikeApp:
    """Mimics FastAPI: a failed body read becomes a 400 response inside the app."""

    async def __call__(self, scope, receive, send) -> None:
        try:
            while True:
                message = await receive()
                if message["type"] != "http.request" or not message.get("more_body"):
                    break
        except Exception:
            await send(
                {"type": "http.response.start", "status": 400, "headers": [(b"content-type", b"application/json")]}
            )
            await send({"type": "http.response.body", "body": b'{"detail":"There was an error parsing the body"}'})
            return
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


@pytest.mark.asyncio
async def test_streamed_overflow_is_reported_as_413_even_when_the_app_answers_400():
    middleware = MaxRequestBodySizeMiddleware(_FastApiLikeApp(), max_body_size=8)
    sent: list[dict] = []
    chunks = [
        {"type": "http.request", "body": b"12345", "more_body": True},
        {"type": "http.request", "body": b"67890", "more_body": True},
    ]

    async def receive():
        return chunks.pop(0)

    async def send(message):
        sent.append(message)

    await middleware(_scope(), receive, send)

    assert sent[0]["status"] == 413
    assert b"Request body too large" in sent[1]["body"]


def _app_with_body_limit(monkeypatch, limit: int) -> TestClient:
    monkeypatch.setattr(middlewares.server_settings, "max_request_body_size", limit)
    app = FastAPI()
    middlewares.setup_middleware(app)

    @app.post("/echo")
    async def echo(request: Request):
        return {"size": len(await request.body())}

    return TestClient(app)


def test_setup_middleware_applies_the_configured_body_limit(monkeypatch):
    client = _app_with_body_limit(monkeypatch, 16)

    assert client.post("/echo", content=b"x" * 16).json() == {"size": 16}
    response = client.post("/echo", content=b"x" * 17)
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}


def test_zero_body_limit_disables_the_check(monkeypatch):
    client = _app_with_body_limit(monkeypatch, 0)

    assert client.post("/echo", content=b"x" * 4096).json() == {"size": 4096}


def test_access_log_redacts_subscription_tokens_and_setup_keys():
    assert redact_log_path("/sub/secret-token") == "/sub/***"
    assert redact_log_path("/api/setup/owner", b"key=abc123") == "/api/setup/owner?key=***"
    assert redact_log_path("/api/admin/token", b"username=admin") == "/api/admin/token?username=admin"
    assert "secret-token" not in redact_log_path("/sub/secret-token/info", b"x=1")


def test_access_log_redacts_encoded_and_mixed_case_secret_names():
    assert redact_log_path("/api", b"%6Bey=abc&Token=def&a=1") == "/api?%6Bey=***&Token=***&a=1"


def test_access_log_keeps_the_query_percent_encoded():
    logged = redact_log_path("/api", b"next=a%0Ab&q=x+y%20z&flag&key=s%0Aecret")

    assert logged == "/api?next=a%0Ab&q=x+y%20z&flag&key=***"
    assert "\n" not in logged
    assert "\r" not in redact_log_path("/api", b"q=%0D%0Afake")
