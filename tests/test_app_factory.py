import json

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.requests import Request

from app.app_factory import database_operational_error_handler, node_revocation_error_handler
from app.node.errors import NodeRevocationError


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
async def test_node_revocation_error_handler_returns_retryable_503():
    request = Request({"type": "http", "method": "DELETE", "path": "/api/user/1", "headers": []})

    response = await node_revocation_error_handler(request, NodeRevocationError("node unavailable"))

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "detail": "User removal was not confirmed by all runtime nodes. Retry when nodes are available."
    }
    assert response.headers["retry-after"] == "1"
