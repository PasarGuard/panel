from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.middlewares.request_logging import RequestProcessTimeLoggingMiddleware
from app.utils.performance import record_phase


@pytest.mark.asyncio
async def test_sampled_access_log_keeps_request_phases_and_redacts_target():
    async def app(scope, receive, send):
        record_phase("database", 12.5)
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(message):
        pass

    async def receive():
        return {"type": "http.request", "body": b""}

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/users/secret-id",
        "query_string": b"token=secret-token",
        "route": SimpleNamespace(path="/users/{id}"),
        "client": ("127.0.0.1", 1234),
        "http_version": "1.1",
    }
    logger = Mock()
    middleware = RequestProcessTimeLoggingMiddleware(
        app,
        logger,
        success_sample_rate=0,
        sampled_routes=frozenset({"/users/{id}"}),
        slow_request_ms=10_000,
    )

    await middleware(scope, receive, send)
    logger.log.assert_not_called()
    logger.info.assert_not_called()

    middleware.success_sample_rate = 1
    await middleware(scope, receive, send)

    logger.log.assert_called_once()
    logger.info.assert_called_once_with("request phases: %s", {"database": 12.5})
    assert "/users/{id}?<redacted>" in logger.log.call_args.args
    assert "secret-token" not in str(logger.mock_calls)
    assert "secret-id" not in str(logger.mock_calls)
