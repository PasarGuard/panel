import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.middlewares import request_logging
from app.middlewares.request_logging import RequestProcessTimeLoggingMiddleware


def _scope(path: str, query: bytes = b"") -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query,
        "http_version": "1.1",
        "client": ("203.0.113.1", 1234),
    }


async def _call_middleware(
    scope: dict,
    *,
    route_path: str | None,
    status_code: int = 200,
    sample_rate: float = 1,
    sampled_routes: frozenset[str] = frozenset(),
) -> Mock:
    async def app(inner_scope, receive, send):
        if route_path is not None:
            inner_scope["route"] = SimpleNamespace(path=route_path)
        await send({"type": "http.response.start", "status": status_code, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(_):
        return None

    logger = Mock()
    middleware = RequestProcessTimeLoggingMiddleware(
        app,
        logger,
        success_sample_rate=sample_rate,
        slow_request_ms=1000,
        sampled_routes=sampled_routes,
    )
    await middleware(scope, receive, send)
    return logger


@pytest.mark.asyncio
async def test_access_log_uses_route_template_and_redacts_query_values():
    logger = await _call_middleware(
        _scope("/sub/secret-token", b"usernames=alice&limit=100"),
        route_path="/sub/{token}",
    )

    args = logger.log.call_args.args
    assert args[0] == logging.INFO
    assert args[4] == "/sub/{token}?<redacted>"
    assert "secret-token" not in args
    assert "alice" not in args


@pytest.mark.asyncio
async def test_unmatched_access_log_never_uses_raw_path():
    logger = await _call_middleware(_scope("/secret/unknown-token"), route_path=None, status_code=404)

    args = logger.log.call_args.args
    assert args[0] == logging.INFO
    assert args[4] == "/<unmatched>"
    assert "unknown-token" not in args


@pytest.mark.asyncio
async def test_frequent_success_is_debug_when_not_sampled():
    route = "/api/user/{username}"
    logger = await _call_middleware(
        _scope("/api/user/alice"),
        route_path=route,
        sample_rate=0,
        sampled_routes=frozenset({route}),
    )

    assert logger.log.call_args.args[0] == logging.DEBUG


@pytest.mark.asyncio
async def test_error_on_frequent_route_is_always_info():
    route = "/api/user/{username}"
    logger = await _call_middleware(
        _scope("/api/user/alice"),
        route_path=route,
        status_code=500,
        sample_rate=0,
        sampled_routes=frozenset({route}),
    )

    assert logger.log.call_args.args[0] == logging.INFO


@pytest.mark.asyncio
async def test_slow_success_on_frequent_route_is_always_info(monkeypatch: pytest.MonkeyPatch):
    times = iter((1.0, 2.1))
    monkeypatch.setattr(request_logging, "perf_counter", lambda: next(times))
    route = "/api/user/{username}"

    logger = await _call_middleware(
        _scope("/api/user/alice"),
        route_path=route,
        sample_rate=0,
        sampled_routes=frozenset({route}),
    )

    assert logger.log.call_args.args[0] == logging.INFO
