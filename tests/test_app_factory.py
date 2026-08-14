import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.requests import Request

from app import app_factory
from app.app_factory import database_operational_error_handler


@pytest.mark.asyncio
async def test_database_operational_error_handler_returns_503():
    request = Request({"type": "http", "method": "GET", "path": "/sub/token", "headers": []})
    exc = OperationalError(None, None, Exception("connection failed"))

    response = await database_operational_error_handler(request, exc)

    assert response.status_code == 503
    assert json.loads(response.body) == {"detail": "Database temporarily unavailable"}


@pytest.mark.asyncio
async def test_database_operational_error_handler_handles_dbapi_errors():
    request = Request({"type": "http", "method": "GET", "path": "/sub/token", "headers": []})
    exc = DBAPIError(None, None, Exception("connection failed"))

    response = await database_operational_error_handler(request, exc)

    assert response.status_code == 503
    assert json.loads(response.body) == {"detail": "Database temporarily unavailable"}


@pytest.mark.asyncio
async def test_database_operational_error_log_redacts_route_values(monkeypatch: pytest.MonkeyPatch):
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/sub/secret-token",
            "query_string": b"username=alice",
            "headers": [],
            "route": SimpleNamespace(path="/sub/{token}"),
        }
    )
    warning = Mock()
    monkeypatch.setattr(app_factory.logger, "warning", warning)

    await database_operational_error_handler(request, OperationalError(None, None, Exception("connection failed")))

    message = warning.call_args.args[0]
    assert "/sub/{token}?<redacted>" in message
    assert "secret-token" not in message
    assert "alice" not in message
