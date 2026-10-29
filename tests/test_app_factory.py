import json

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.requests import Request

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
async def test_node_role_clears_general_settings_cache_on_settings_message(monkeypatch: pytest.MonkeyPatch):
    from unittest.mock import AsyncMock

    from app import app_factory, settings as app_settings
    from app.nats.message import MessageTopic

    handlers = {}
    monkeypatch.setattr(
        app_factory.router, "register_handler", lambda topic, handler: handlers.setdefault(topic, handler)
    )
    monkeypatch.setattr("app.node.manager_sync.register_node_sync_handler", lambda: None)

    # A node-only worker runs the usage jobs but not the full settings handler (which also syncs the bot)
    app_factory._register_nats_handlers(
        enable_router=False, enable_settings=False, enable_client_templates=False, enable_node_sync=True
    )

    clear = AsyncMock()
    monkeypatch.setattr(app_settings.general_settings.cache, "clear", clear)
    await handlers[MessageTopic.SETTING]({"action": "refresh"})
    clear.assert_awaited_once()
