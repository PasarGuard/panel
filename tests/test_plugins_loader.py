"""Plugin loading, version constraints, broken plugins, events, jobs, schema (no HTTP)."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.plugins import events, manager, registry, schema
from app.plugins.context import PluginContext
from app.plugins.loader import PluginLoadError, check_panel_version
from app.scheduler import scheduler
from tests.plugin_helpers import make_plugin, reset_plugins, route_paths

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def clean_plugins():
    reset_plugins()
    yield
    reset_plugins()


GOOD_PLUGIN = """
from . import helper

def setup(ctx):
    ctx.on("user.created", helper.remember)
"""
HELPER = """
calls = []

async def remember(payload):
    calls.append(payload)
"""


def _load(plugins_dir, ids, *, runs_panel=True, runs_scheduler=True):
    manager.load_all(plugins_dir, ids, runs_panel=runs_panel, runs_scheduler=runs_scheduler)


def test_loads_plugin_as_isolated_package(tmp_path, clean_plugins):
    make_plugin(tmp_path, "good", GOOD_PLUGIN, files={"helper.py": HELPER})
    path_before = list(sys.path)

    _load(tmp_path, ["good"])

    record = registry.records["good"]
    assert record.status == "loaded", record.error
    assert [ctx.id for ctx in registry.active] == ["good"]
    assert "pasarguard_plugins.good.plugin" in sys.modules
    assert "pasarguard_plugins.good.helper" in sys.modules
    assert sys.path == path_before


def test_panel_version_constraint_refused(tmp_path, clean_plugins):
    make_plugin(
        tmp_path,
        "future",
        "def setup(ctx):\n    raise AssertionError('must not run')\n",
        manifest={"panel": ">=99.0.0"},
    )

    _load(tmp_path, ["future"])

    record = registry.records["future"]
    assert record.status == "failed"
    assert "requires panel >=99.0.0" in record.error
    assert registry.active == []
    assert "pasarguard_plugins.future.plugin" not in sys.modules


def test_version_constraint_parsing():
    check_panel_version(">=5.5.0,<6", "5.5.0")
    check_panel_version(None, "5.5.0")
    with pytest.raises(PluginLoadError):
        check_panel_version("<5.5.0", "5.5.0")
    with pytest.raises(PluginLoadError):
        check_panel_version("not a version", "5.5.0")


def test_broken_plugins_are_skipped_and_listed(tmp_path, clean_plugins):
    make_plugin(tmp_path, "syntax", "def setup(ctx)\n    pass\n")
    make_plugin(tmp_path, "raises", "def setup(ctx):\n    ctx.on('*', print)\n    raise RuntimeError('boom')\n")
    make_plugin(tmp_path, "mismatch", "def setup(ctx):\n    pass\n", manifest={"id": "other"})
    make_plugin(tmp_path, "good", GOOD_PLUGIN, files={"helper.py": HELPER})

    _load(tmp_path, ["syntax", "raises", "missing", "mismatch", "Bad/Id", "good"])

    statuses = {plugin_id: record.status for plugin_id, record in registry.records.items()}
    assert statuses == {
        "syntax": "failed",
        "raises": "failed",
        "missing": "failed",
        "mismatch": "failed",
        "Bad/Id": "failed",
        "good": "loaded",
    }
    assert registry.records["raises"].error == "boom"
    assert "not found" in registry.records["missing"].error
    assert "does not match" in registry.records["mismatch"].error
    # A failed setup leaves no handlers behind
    assert [ctx.id for ctx in registry.active] == ["good"]
    assert events.handlers_for("user.created") and len(events.handlers_for("user.created")) == 1


async def test_async_setup_runs_at_startup(tmp_path, clean_plugins):
    make_plugin(
        tmp_path,
        "late",
        """
        import asyncio

        async def setup(ctx):
            await asyncio.sleep(0)

            @ctx.router.get("/ping")
            async def ping():
                return {"ok": True}
        """,
    )
    app = FastAPI()
    _load(tmp_path, ["late"])
    assert registry.active == []

    await manager.finish_pending_setups(app)

    assert [ctx.id for ctx in registry.active] == ["late"]
    assert "/api/plugins/late/ping" in route_paths(app.routes)


async def test_event_handler_payload_and_isolation(clean_plugins, monkeypatch):
    monkeypatch.setattr(events, "HANDLER_TIMEOUT", 0.2)
    ctx = PluginContext("demo", "1.0.0")
    received: list[dict] = []

    async def good(payload):
        payload["mutated"] = True
        received.append(payload)

    async def broken(payload):
        raise RuntimeError("handler failure")

    async def slow(payload):
        await asyncio.sleep(30)

    ctx.on("admin.login", good)
    ctx.on("admin.login", broken)
    ctx.on("*", slow)
    ctx.on("*", good)
    registry.active.append(ctx)

    async def admin_login(username: str, password: str, client_ip: str, success: bool):
        return None

    loop = asyncio.get_running_loop()
    started = loop.time()
    events.emit_notification("admin_login", admin_login, ("root", "secret-password", "1.2.3.4", False), {})
    await events.drain()

    assert loop.time() - started < 5
    assert len(received) == 2
    for payload in received:
        assert payload["event"] == "admin.login"
        assert payload["username"] == "root"
        assert payload["success"] is False
        assert "password" not in payload
        assert "secret-password" not in str(payload)


def test_jobs_registered_only_in_scheduler_role(tmp_path, clean_plugins):
    code = """
    def setup(ctx):
        def tick():
            pass

        ctx.job(tick, seconds=60)
        ctx.job(tick, cron="0 9 * * *")
    """
    make_plugin(tmp_path, "jobs", code)
    app = FastAPI()

    _load(tmp_path, ["jobs"], runs_scheduler=False)
    manager.activate(app, registry.active[0])
    assert [job.id for job in scheduler.get_jobs() if job.id.startswith("plugin:jobs:")] == []

    registry.reset()
    _load(tmp_path, ["jobs"], runs_scheduler=True)
    manager.activate(app, registry.active[0])
    try:
        job_ids = sorted(job.id for job in scheduler.get_jobs() if job.id.startswith("plugin:jobs:"))
        assert job_ids == ["plugin:jobs:tick:0", "plugin:jobs:tick:1"]
    finally:
        for job_id in ("plugin:jobs:tick:0", "plugin:jobs:tick:1"):
            if scheduler.get_job(job_id):
                scheduler.remove_job(job_id)


def test_job_after_setup_is_rejected():
    ctx = PluginContext("demo", "1.0.0")
    ctx.activated = True
    with pytest.raises(RuntimeError):
        ctx.job(lambda: None, seconds=10)


def test_routes_are_not_mounted_outside_panel_role(tmp_path, clean_plugins):
    code = """
    def setup(ctx):
        @ctx.router.get("/x")
        async def x():
            return {}
    """
    make_plugin(tmp_path, "nopanel", code)
    app = FastAPI()
    _load(tmp_path, ["nopanel"], runs_panel=False)
    manager.activate(app, registry.active[0])
    assert not [path for path in route_paths(app.routes) if path.startswith("/api/plugins/")]


def test_schema_defaults_and_validation():
    settings_schema = {
        "type": "object",
        "properties": {
            "days": {"type": "integer", "default": 7, "minimum": 1, "maximum": 30},
            "mode": {"type": "string", "enum": ["a", "b"], "default": "a"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "nested": {"type": "object", "properties": {"on": {"type": "boolean", "default": True}}},
        },
        "required": ["days"],
        "additionalProperties": False,
    }
    assert schema.apply_defaults(settings_schema, {}) == {"days": 7, "mode": "a", "nested": {"on": True}}
    assert schema.validate(settings_schema, {"days": 7, "mode": "a", "tags": ["x"]}) == []

    errors = schema.validate(
        settings_schema, {"days": 0, "mode": "c", "tags": [1], "extra": 1, "nested": {"on": "yes"}}
    )
    assert "days: must be >= 1" in errors
    assert any(error.startswith("mode: must be one of") for error in errors)
    assert "tags[0]: expected string" in errors
    assert "extra: unknown property" in errors
    assert "nested.on: expected boolean" in errors
    assert schema.validate(settings_schema, {}) == ["days: is required"]
    assert schema.validate(settings_schema, {"days": True}) == ["days: expected integer"]
    # Unknown keys are allowed unless additionalProperties is false
    assert schema.validate({"type": "object", "properties": {}}, {"anything": 1}) == []


def test_plugins_empty_imports_nothing():
    """PLUGINS unset: no plugin module, no plugin manager import, no plugin routes."""
    script = (
        "import sys\n"
        "from app.app_factory import create_app\n"
        "def route_paths(routes):\n"
        "    out = []\n"
        "    for r in routes:\n"
        "        if hasattr(r, 'effective_candidates'):\n"
        "            out += route_paths(r.effective_candidates())\n"
        "        elif getattr(r, 'path', None) is not None:\n"
        "            out.append(r.path)\n"
        "    return out\n"
        "app = create_app()\n"
        "from app.plugins import registry\n"
        "routes = [p for p in route_paths(app.routes) if p.startswith('/api/plugins/')]\n"
        "core = {'/api/plugins/sdk.js', '/api/plugins/{plugin_id}/settings',"
        " '/api/plugins/{plugin_id}/ui-session', '/api/plugins/{plugin_id}/ui/{file_path:path}'}\n"
        "assert set(routes) <= core, routes\n"
        "assert not [m for m in sys.modules if m.startswith('pasarguard_plugins')]\n"
        "assert 'app.plugins.manager' not in sys.modules\n"
        "assert 'app.plugins.loader' not in sys.modules\n"
        "assert registry.active == [] and registry.records == {}\n"
        "print('OK')\n"
    )
    env = {**os.environ, "PLUGINS": "", "PLUGINS_DIR": str(PROJECT_ROOT / "examples" / "plugins")}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().endswith("OK")
