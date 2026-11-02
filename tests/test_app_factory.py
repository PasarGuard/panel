import json

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


class _RecordingRouter:
    def __init__(self):
        self.handlers = {}

    def register_handler(self, topic, handler):
        self.handlers[topic] = handler


@pytest.mark.parametrize(
    ("enable_settings", "enable_refresh", "expected"),
    [
        (True, True, "handle_settings_message"),
        (False, True, "_refresh_settings_message"),
        (False, False, None),
    ],
)
def test_settings_messages_reach_node_workers_without_the_bot(monkeypatch, enable_settings, enable_refresh, expected):
    fake_router = _RecordingRouter()
    monkeypatch.setattr(app_factory, "router", fake_router)
    monkeypatch.setattr(app_factory, "on_startup", lambda func: func)
    monkeypatch.setattr(app_factory, "on_shutdown", lambda func: func)

    app_factory._register_nats_handlers(
        enable_router=False,
        enable_settings=enable_settings,
        enable_client_templates=False,
        enable_settings_refresh=enable_refresh,
    )

    handler = fake_router.handlers.get(app_factory.MessageTopic.SETTING)
    assert (handler.__name__ if handler else None) == expected
