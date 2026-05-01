from unittest.mock import MagicMock

import pytest
from aiorwlock import RWLock

from . import GetTestDB, client


@pytest.fixture(autouse=True)
def mock_db_session(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.settings.GetDB", GetTestDB)
    monkeypatch.setattr("app.subscription.client_templates.GetDB", GetTestDB)
    return None


@pytest.fixture(autouse=True)
def mock_lock(monkeypatch: pytest.MonkeyPatch):
    _lock = MagicMock(spec=RWLock(fast=True))
    monkeypatch.setattr("app.node.node_manager._lock", _lock)


@pytest.fixture
def access_token() -> str:
    response = client.post(
        url="/api/admin/token",
        data={"username": "testadmin", "password": "testadmin", "grant_type": "password"},
    )
    return response.json()["access_token"]


@pytest.fixture
def disable_cache(monkeypatch: pytest.MonkeyPatch):
    def dummy_cached(*args, **kwargs):
        def wrapper(func):
            return func  # bypass caching

        return wrapper

    monkeypatch.setattr("app.settings.cached", dummy_cached)
