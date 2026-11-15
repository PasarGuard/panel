import json
import warnings

import pytest
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.requests import Request

from app import app_factory
from app.app_factory import database_operational_error_handler
from role import Role


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
        self.resync_handlers = {}

    def register_handler(self, topic, handler):
        self.handlers[topic] = handler

    def register_resync_handler(self, topic, handler):
        self.resync_handlers[topic] = handler


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
    # A reconnect refreshes settings the same way, so node workers never start the bot then either
    resync = fake_router.resync_handlers.get(app_factory.MessageTopic.SETTING)
    resync_name = getattr(resync, "func", resync).__name__ if resync else None
    assert resync_name == {"_refresh_settings_message": "refresh_caches"}.get(expected, expected)


@pytest.mark.parametrize("role", list(Role))
def test_notification_dedup_is_closed_on_shutdown_for_every_role(monkeypatch, role):
    import dashboard
    from app.notification.dedup import close_notification_dedup

    shutdown = []
    monkeypatch.setattr(app_factory.runtime_settings, "role", role)
    monkeypatch.setattr(app_factory, "require_nats_if_multiworker", lambda *_: None)
    monkeypatch.setattr(app_factory, "setup_middleware", lambda *_: None)
    monkeypatch.setattr(app_factory, "_register_nats_handlers", lambda *_, **__: None)
    monkeypatch.setattr(app_factory, "_register_scheduler_hooks", lambda: None)
    monkeypatch.setattr(app_factory, "_register_jobs", lambda: None)
    monkeypatch.setattr(app_factory, "on_startup", lambda func: func)
    monkeypatch.setattr(app_factory, "on_shutdown", shutdown.append)
    monkeypatch.setattr(dashboard, "setup_dashboard", lambda *_: None)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        app_factory.create_app()

    assert close_notification_dedup in shutdown
