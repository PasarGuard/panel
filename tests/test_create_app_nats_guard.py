import pytest

from app.nats import is_multi_worker, require_nats_if_multiworker
from role import Role


def test_is_multi_worker_true_for_all_in_one_with_many_workers(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.nats.runtime_settings.role", Role.ALL_IN_ONE)
    monkeypatch.setattr("app.nats.server_settings.workers", 2)
    monkeypatch.setattr("app.nats.nats_settings.enabled", False)
    assert is_multi_worker() is True


def test_require_nats_if_multiworker_fails_fast_without_nats(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.nats.nats_settings.enabled", False)
    with pytest.raises(RuntimeError, match="NATS is required"):
        require_nats_if_multiworker(True)


def test_warn_deprecated_role_uses_is_deprecated(monkeypatch: pytest.MonkeyPatch):
    from app import app_factory

    warned: list[str] = []

    def _warn(message, category, stacklevel=1):
        warned.append(message)

    monkeypatch.setattr("app.app_factory.runtime_settings.role", Role.BACKEND)
    monkeypatch.setattr("app.app_factory.warnings.warn", _warn)
    monkeypatch.setattr(app_factory.logger, "warning", lambda *_a, **_k: None)

    app_factory._warn_deprecated_role()
    assert warned
    assert "deprecated" in warned[0]

    warned.clear()
    monkeypatch.setattr("app.app_factory.runtime_settings.role", Role.ALL_IN_ONE)
    app_factory._warn_deprecated_role()
    assert warned == []
