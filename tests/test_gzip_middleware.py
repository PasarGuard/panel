import gzip
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from sse_starlette.sse import EventSourceResponse

from app import middlewares

BIG_HTML = "<html>" + "<p>subscription page</p>" * 500 + "</html>"


def _app(monkeypatch, enabled: bool = True, minimum_size: int = 1000) -> TestClient:
    settings = SimpleNamespace(
        gzip_enabled=enabled, gzip_minimum_size=minimum_size, proxy_headers=False, forwarded_allow_ips="127.0.0.1"
    )
    monkeypatch.setattr(middlewares, "server_settings", settings)
    app = FastAPI()
    middlewares.setup_middleware(app)
    app.get("/page")(lambda: HTMLResponse(BIG_HTML))
    app.get("/small")(lambda: {"ok": True})

    async def events():
        yield {"data": "x" * 2000}

    app.get("/events")(lambda: EventSourceResponse(events()))
    return TestClient(app)


def _raw_get(client: TestClient, path: str, accept_encoding: str = "gzip"):
    # Read the raw stream so httpx does not decode the body for us.
    with client.stream("GET", path, headers={"Accept-Encoding": accept_encoding}) as response:
        return response, b"".join(response.iter_raw())


def test_large_response_is_gzipped(monkeypatch):
    response, body = _raw_get(_app(monkeypatch), "/page")

    assert response.headers["content-encoding"] == "gzip"
    assert "Accept-Encoding" in response.headers["vary"]
    assert gzip.decompress(body).decode() == BIG_HTML
    assert len(body) < len(BIG_HTML)


@pytest.mark.parametrize("path", ["/small", "/events"])
def test_small_and_sse_responses_are_not_gzipped(monkeypatch, path):
    response, _ = _raw_get(_app(monkeypatch), path)

    assert "content-encoding" not in response.headers


def test_no_gzip_without_accept_encoding(monkeypatch):
    response, body = _raw_get(_app(monkeypatch), "/page", accept_encoding="identity")

    assert "content-encoding" not in response.headers
    assert body.decode() == BIG_HTML


def test_gzip_can_be_disabled(monkeypatch):
    response, body = _raw_get(_app(monkeypatch, enabled=False), "/page")

    assert "content-encoding" not in response.headers
    assert body.decode() == BIG_HTML
