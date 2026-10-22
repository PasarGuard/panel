from unittest.mock import MagicMock

import pytest

import dashboard


@pytest.mark.parametrize("missing", ["index", "statics"])
def test_partial_dashboard_build_is_not_treated_as_ready(monkeypatch, tmp_path, missing):
    build = tmp_path / "build"
    build.mkdir()
    if missing != "index":
        (build / "index.html").write_text("ready")
    if missing != "statics":
        (build / "statics").mkdir()
    monkeypatch.setattr(dashboard, "build_dir", build)
    monkeypatch.setattr(dashboard, "statics_dir", build / "statics")

    def finish_build():
        (build / "index.html").write_text("ready")
        (build / "statics").mkdir(exist_ok=True)

    rebuild = MagicMock(side_effect=finish_build)
    monkeypatch.setattr(dashboard, "build", rebuild)
    app = MagicMock()
    dashboard.run_build(app)
    rebuild.assert_called_once_with()
    assert app.mount.call_count == 2


def test_complete_dashboard_does_not_require_bun(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("ready")
    (tmp_path / "statics").mkdir()
    monkeypatch.setattr(dashboard, "build_dir", tmp_path)
    monkeypatch.setattr(dashboard, "statics_dir", tmp_path / "statics")
    rebuild = MagicMock()
    monkeypatch.setattr(dashboard, "build", rebuild)
    dashboard.run_build(MagicMock())
    rebuild.assert_not_called()


@pytest.mark.asyncio
async def test_dashboard_hook_uses_running_app_not_previously_created_app(monkeypatch):
    from fastapi import FastAPI

    hooks = []
    monkeypatch.setattr(dashboard, "on_startup", hooks.append)
    monkeypatch.setattr(dashboard.runtime_settings, "debug", False)
    build = MagicMock()
    monkeypatch.setattr(dashboard, "run_build", build)
    first, second = FastAPI(), FastAPI()
    dashboard.setup_dashboard(first)
    dashboard.setup_dashboard(second)
    assert hooks[0] is hooks[1]
    hooks[0](second)
    build.assert_called_once_with(second)
