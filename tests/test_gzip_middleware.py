import gzip
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse

from app import middlewares
from app.middlewares.gzip import accepts_gzip
from config import ServerSettings

BIG_HTML = "<html>" + "<p>subscription page</p>" * 500 + "</html>"


def _app(monkeypatch, enabled: bool = True, minimum_size: int = 1000, file_path=None) -> TestClient:
    settings = SimpleNamespace(
        gzip_enabled=enabled, gzip_minimum_size=minimum_size, proxy_headers=False, forwarded_allow_ips="127.0.0.1"
    )
    monkeypatch.setattr(middlewares, "server_settings", settings)
    app = FastAPI()
    middlewares.setup_middleware(app)
    app.get("/page")(lambda: HTMLResponse(BIG_HTML))
    app.get("/small")(lambda: {"ok": True})
    if file_path is not None:
        app.get("/file")(lambda: FileResponse(file_path))
        app.mount("/static", StaticFiles(directory=file_path.parent))

    async def events():
        yield {"data": "x" * 2000}

    app.get("/events")(lambda: EventSourceResponse(events()))
    return TestClient(app)


def _raw_get(client: TestClient, path: str, accept_encoding: str = "gzip", **headers: str):
    # Read the raw stream so httpx does not decode the body for us.
    with client.stream("GET", path, headers={"Accept-Encoding": accept_encoding, **headers}) as response:
        return response, b"".join(response.iter_raw())


@pytest.mark.parametrize("accept_encoding", ["gzip", "GZIP;q=0.5", "br, gzip"])
def test_large_response_is_gzipped(monkeypatch, accept_encoding):
    response, body = _raw_get(_app(monkeypatch), "/page", accept_encoding=accept_encoding)

    assert response.headers["content-encoding"] == "gzip"
    assert "Accept-Encoding" in response.headers["vary"]
    assert gzip.decompress(body).decode() == BIG_HTML
    assert len(body) < len(BIG_HTML)


@pytest.mark.parametrize("path", ["/small", "/events"])
def test_small_and_sse_responses_are_not_gzipped(monkeypatch, path):
    response, _ = _raw_get(_app(monkeypatch), path)

    assert "content-encoding" not in response.headers


@pytest.mark.parametrize("accept_encoding", ["identity", "gzip;q=0", "br, gzip; q=0.0"])
def test_no_gzip_unless_accepted(monkeypatch, accept_encoding):
    response, body = _raw_get(_app(monkeypatch), "/page", accept_encoding=accept_encoding)

    assert "content-encoding" not in response.headers
    assert body.decode() == BIG_HTML


def test_gzip_can_be_disabled(monkeypatch):
    response, body = _raw_get(_app(monkeypatch, enabled=False), "/page")

    assert "content-encoding" not in response.headers
    assert body.decode() == BIG_HTML


@pytest.mark.parametrize(
    ("accept_encoding", "expected"),
    [
        ("gzip", True),
        ("deflate, GZIP;q=0.5", True),
        ("gzip;q=0", False),
        ("gzip;q=bad", False),
        ("x-gzip", False),
        ("", False),
    ],
)
def test_accepts_gzip(accept_encoding, expected):
    assert accepts_gzip(accept_encoding) is expected


def test_range_response_is_not_gzipped(monkeypatch, tmp_path):
    asset = tmp_path / "app.js"
    asset.write_text(BIG_HTML)

    response, body = _raw_get(_app(monkeypatch, file_path=asset), "/file", Range="bytes=0-1999")

    assert response.status_code == 206
    assert "content-encoding" not in response.headers
    assert body.decode() == BIG_HTML[:2000]


def test_zero_minimum_size_is_rejected(monkeypatch):
    monkeypatch.setenv("GZIP_MINIMUM_SIZE", "0")

    with pytest.raises(ValidationError):
        ServerSettings()


def test_gzipped_file_gets_weak_etag_and_if_range_falls_back_to_full_body(monkeypatch, tmp_path):
    asset = tmp_path / "app.js"
    asset.write_text(BIG_HTML)
    client = _app(monkeypatch, file_path=asset)

    identity, _ = _raw_get(client, "/file", accept_encoding="identity")
    gzipped, _ = _raw_get(client, "/file")
    assert gzipped.headers["content-encoding"] == "gzip"
    assert gzipped.headers["etag"] == f"W/{identity.headers['etag']}"

    # Resuming the gzipped body must not return a slice of the identity file.
    resumed, body = _raw_get(client, "/file", Range="bytes=100-", **{"If-Range": gzipped.headers["etag"]})
    assert resumed.status_code == 200
    assert body.decode() == BIG_HTML

    # Conditional requests still revalidate against the weak tag.
    not_modified, _ = _raw_get(client, "/static/app.js", **{"If-None-Match": gzipped.headers["etag"]})
    assert not_modified.status_code == 304
