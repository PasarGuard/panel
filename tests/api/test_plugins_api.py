"""Plugin system through the HTTP API: routes + auth, events, subscription hooks, settings, UI files."""

import asyncio
import base64
import pathlib
import sys
import time
from urllib.parse import quote

import pytest
from fastapi import status
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.db.models import PluginSettings
from app.models.notification_enable import NotificationEnable
from app.plugins import events, manager, registry, settings as plugin_settings_module
from app.scheduler import scheduler
from app.subscription.config_cache import clear_sub_config_cache
from tests.api import GetTestDB, TestSession, app, client
from tests.api.helpers import (
    auth_headers,
    create_admin,
    create_core,
    create_group,
    create_user,
    delete_admin,
    delete_core,
    delete_group,
    delete_user,
    get_inbounds,
    unique_name,
)
from tests.plugin_helpers import make_plugin, reset_plugins

PROBE = """
import asyncio

from fastapi import Depends

calls = {"events": [], "cached": 0, "uncached": 0, "changes": []}


def setup(ctx):
    @ctx.router.get("/secret")
    async def secret():
        return {"ok": True}

    @ctx.router.get("/owner-only", dependencies=[Depends(ctx.deps.owner)])
    async def owner_only():
        return {"ok": True}

    @ctx.router.get("/public", dependencies=[Depends(ctx.deps.public)])
    async def public():
        return {"public": True}

    async def remember(payload):
        calls["events"].append(payload)

    async def broken(payload):
        raise RuntimeError("plugin handler failure")

    async def slow(payload):
        await asyncio.sleep(30)

    ctx.on("user.created", remember)
    ctx.on("user.created", broken)
    ctx.on("user.created", slow)
    ctx.on("admin.login", remember)

    @ctx.subscription.transform
    def banner(user, config_format, content):
        calls["cached"] += 1
        if config_format not in ("links", "links_base64"):
            return None
        return f"# banner {user['username']} {config_format}\\n{content}"

    @ctx.subscription.transform(cache=False)
    def hits(user, config_format, content):
        calls["uncached"] += 1
        if config_format not in ("links", "links_base64"):
            return None
        return f"{content}\\n# hits {calls['uncached']}"

    @ctx.subscription.headers
    def headers(user, config_format, headers):
        return {"x-plugin-format": str(config_format), "profile-title": "overridden by plugin"}

    @ctx.subscription.variables
    def variables(user):
        return {"PLAN": "gold", "USERNAME": "hijacked", "lowercase": "ignored"}

    ctx.settings.on_change(lambda values: calls["changes"].append(values))
"""

SETTINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "days": {"type": "integer", "default": 7, "minimum": 1},
        "label": {"type": "string", "default": "x"},
    },
    "additionalProperties": False,
}


@pytest.fixture
def probe(tmp_path, monkeypatch):
    reset_plugins()
    # The subscription cache is keyed by user id, and SQLite reuses ids of deleted users
    clear_sub_config_cache()
    monkeypatch.setattr(events, "HANDLER_TIMEOUT", 0.5)
    make_plugin(
        tmp_path,
        "probe",
        PROBE,
        manifest={"settings_schema": SETTINGS_SCHEMA, "ui": "ui/index.html", "description": "test probe"},
        files={"ui/index.html": "<html>probe ui</html>", "ui/app.js": "console.log('probe')"},
    )
    make_plugin(tmp_path, "broken", "def setup(ctx):\n    raise RuntimeError('broken on purpose')\n")
    routes_before = len(app.router.routes)
    manager.load_all(tmp_path, ["probe", "broken"], runs_panel=True, runs_scheduler=False)
    for ctx in registry.active:
        manager.activate(app, ctx)
    yield sys.modules["pasarguard_plugins.probe.plugin"].calls
    del app.router.routes[routes_before:]
    app.router._mark_routes_changed()
    reset_plugins()
    clear_sub_config_cache()
    client.cookies.clear()


@pytest.fixture
def plain_admin(access_token):
    admin = create_admin(access_token)
    response = client.post(
        "/api/admin/token",
        data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
    )
    assert response.status_code == status.HTTP_200_OK
    yield response.json()["access_token"]
    delete_admin(access_token, admin["username"])


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _all_notifications_off() -> NotificationEnable:
    enable = NotificationEnable()
    for name in type(enable).model_fields:
        section = getattr(enable, name)
        if isinstance(section, bool):
            setattr(enable, name, False)
            continue
        for field in type(section).model_fields:
            if isinstance(getattr(section, field), bool):
                setattr(section, field, False)
    return enable


def test_list_plugins_is_owner_only(probe, access_token, plain_admin):
    response = client.get("/api/plugins", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK
    plugins = {plugin["id"]: plugin for plugin in response.json()["plugins"]}
    assert plugins["probe"]["status"] == "loaded"
    assert plugins["probe"]["has_ui"] is True
    assert plugins["probe"]["settings_schema"] == SETTINGS_SCHEMA
    assert plugins["broken"]["status"] == "failed"
    assert plugins["broken"]["error"] == "broken on purpose"
    assert plugins["broken"]["has_ui"] is False

    assert client.get("/api/plugins", headers=auth_headers(plain_admin)).status_code == status.HTTP_403_FORBIDDEN
    assert client.get("/api/plugins").status_code == status.HTTP_401_UNAUTHORIZED


def test_plugin_routes_require_admin_unless_public(probe, access_token, plain_admin):
    assert client.get("/api/plugins/probe/secret").status_code == status.HTTP_401_UNAUTHORIZED
    assert client.get("/api/plugins/probe/secret", headers=auth_headers(plain_admin)).json() == {"ok": True}

    owner_only = "/api/plugins/probe/owner-only"
    assert client.get(owner_only, headers=auth_headers(plain_admin)).status_code == status.HTTP_403_FORBIDDEN
    assert client.get(owner_only, headers=auth_headers(access_token)).status_code == status.HTTP_200_OK

    assert client.get("/api/plugins/probe/public").json() == {"public": True}
    # Failed plugins mount nothing
    assert client.get("/api/plugins/broken/secret", headers=auth_headers(access_token)).status_code == 404


def test_user_created_event_reaches_plugin_once_with_notifications_off(probe, access_token, monkeypatch):
    async def notifications_off():
        return _all_notifications_off()

    monkeypatch.setattr("app.notification.notification_enable", notifications_off)
    username = unique_name("plugin_event_user")

    user = create_user(access_token, payload={"username": username})  # asserts 201 despite failing/slow handlers
    try:
        assert _wait_for(lambda: any(e["event"] == "user.created" for e in probe["events"]))
        time.sleep(0.3)
        created = [e for e in probe["events"] if e["event"] == "user.created"]
        assert len(created) == 1
        assert created[0]["user"]["username"] == username
        assert created[0]["user"]["id"] == user["id"]
        assert created[0]["by"] == "testadmin"
    finally:
        delete_user(access_token, username)


def test_admin_login_event_has_no_password(probe):
    wrong = client.post(
        "/api/admin/token",
        data={"username": "testadmin", "password": "Wrong-Pass-12345", "grant_type": "password"},
    )
    assert wrong.status_code == status.HTTP_401_UNAUTHORIZED
    ok = client.post(
        "/api/admin/token", data={"username": "testadmin", "password": "testadmin", "grant_type": "password"}
    )
    assert ok.status_code == status.HTTP_200_OK

    assert _wait_for(lambda: len([e for e in probe["events"] if e["event"] == "admin.login"]) >= 2)
    logins = [e for e in probe["events"] if e["event"] == "admin.login"]
    assert {e["success"] for e in logins} == {True, False}
    for payload in logins:
        assert payload["username"] == "testadmin"
        assert "password" not in payload
        assert "Wrong-Pass-12345" not in str(payload)


def test_subscription_transform_headers_and_cache(probe, access_token):
    username = unique_name("plugin_sub_user")
    user = create_user(access_token, payload={"username": username})
    try:
        first = client.get(f"{user['subscription_url']}/links")
        assert first.status_code == status.HTTP_200_OK
        assert first.text.startswith(f"# banner {username} links")
        assert first.text.endswith("# hits 1")
        assert first.headers["x-plugin-format"] == "links"
        assert probe["cached"] == 1

        # Served from the subscription cache: cached transform not re-run, uncached one runs again
        second = client.get(f"{user['subscription_url']}/links")
        assert second.text.startswith(f"# banner {username} links")
        assert second.text.endswith("# hits 2")
        assert probe["cached"] == 1

        encoded = client.get(f"{user['subscription_url']}/links_base64")
        assert encoded.status_code == status.HTTP_200_OK
        decoded = base64.b64decode(encoded.text).decode()
        assert decoded.startswith(f"# banner {username} links_base64")
        assert decoded.endswith("# hits 3")
        assert encoded.headers["x-plugin-format"] == "links_base64"
    finally:
        delete_user(access_token, username)


def test_subscription_variables_in_host_remarks(probe, access_token):
    core = create_core(access_token)
    inbound = next(tag for tag in get_inbounds(access_token) if "VLESS" in tag.upper())
    group = create_group(access_token, name=unique_name("plugin_var_group"), inbound_tags=[inbound])
    remark = f"{{PLAN}}-{{USERNAME}}-{unique_name('r')}"
    host = client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={"remark": remark, "address": ["plugin.example.com"], "port": 443, "inbound_tag": inbound, "priority": 1},
    )
    assert host.status_code == status.HTTP_201_CREATED, host.text
    username = unique_name("plugin_var_user")
    user = create_user(access_token, group_ids=[group["id"]], payload={"username": username})
    try:
        links = client.get(f"{user['subscription_url']}/links").text
        expected = remark.replace("{PLAN}", "gold").replace("{USERNAME}", username)
        assert quote(expected, safe="") in links or expected in links
        assert "hijacked" not in links
    finally:
        delete_user(access_token, username)
        client.delete(f"/api/host/{host.json()['id']}", headers=auth_headers(access_token))
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_plugin_settings_get_put_validation(probe, access_token, plain_admin, monkeypatch):
    url = "/api/plugins/probe/settings"
    assert client.get(url, headers=auth_headers(access_token)).json() == {"days": 7, "label": "x"}
    assert client.get(url, headers=auth_headers(plain_admin)).status_code == status.HTTP_403_FORBIDDEN
    assert client.get("/api/plugins/broken/settings", headers=auth_headers(access_token)).status_code == 404
    assert client.get("/api/plugins/nope/settings", headers=auth_headers(access_token)).status_code == 404

    invalid = client.put(url, headers=auth_headers(access_token), json={"days": 0})
    assert invalid.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert invalid.json()["detail"] == {"days": "must be >= 1"}
    unknown = client.put(url, headers=auth_headers(access_token), json={"days": 3, "extra": True})
    assert unknown.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert probe["changes"] == []

    saved = client.put(url, headers=auth_headers(access_token), json={"days": 3})
    assert saved.status_code == status.HTTP_200_OK
    assert saved.json() == {"days": 3, "label": "x"}
    assert probe["changes"] == [{"days": 3, "label": "x"}]
    assert registry.get_active("probe").settings.get() == {"days": 3, "label": "x"}
    assert client.get(url, headers=auth_headers(access_token)).json() == {"days": 3, "label": "x"}

    async def stored():
        async with TestSession() as session:
            row = (
                await session.execute(select(PluginSettings).where(PluginSettings.plugin_id == "probe"))
            ).scalar_one()
            return row.data

    assert asyncio.run(stored()) == {"days": 3, "label": "x"}

    # Another worker's NATS refresh: reload from the database and fire on_change there
    monkeypatch.setattr(plugin_settings_module, "GetDB", GetTestDB)
    ctx = registry.get_active("probe")
    ctx.settings.set_values(ctx.settings.defaults())
    asyncio.run(plugin_settings_module.handle_plugin_message({"action": "settings", "plugin_id": "probe"}))
    assert ctx.settings.get() == {"days": 3, "label": "x"}
    assert probe["changes"][-1] == {"days": 3, "label": "x"}


def test_plugin_ui_files_need_owner_and_block_traversal(probe, access_token, plain_admin):
    index = "/api/plugins/probe/ui/"
    assert client.get(index).status_code == status.HTTP_401_UNAUTHORIZED
    assert client.get(index, headers=auth_headers(plain_admin)).status_code == status.HTTP_403_FORBIDDEN
    owner = client.get(index, headers=auth_headers(access_token))
    assert owner.status_code == status.HTTP_200_OK
    assert "probe ui" in owner.text
    assert client.get("/api/plugins/probe/ui/app.js", headers=auth_headers(access_token)).status_code == 200

    for path in ("..%2fplugin.py", "%2e%2e/plugin.json", "..%2F..%2Fplugin.py", "%2e%2e%2f%2e%2e%2fconfig.py"):
        response = client.get(f"/api/plugins/probe/ui/{path}", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_404_NOT_FOUND, path
    assert client.get("/api/plugins/broken/ui/", headers=auth_headers(access_token)).status_code == 404

    # The dashboard sets a path-scoped cookie so the iframe can load files without headers
    assert client.post("/api/plugins/probe/ui-session", headers=auth_headers(plain_admin)).status_code == 403
    session = client.post("/api/plugins/probe/ui-session", headers=auth_headers(access_token))
    assert session.status_code == status.HTTP_204_NO_CONTENT
    cookie = session.headers["set-cookie"]
    assert "Path=/api/plugins/probe/ui/" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Secure" in cookie
    https_index = f"https://testserver{index}"
    assert client.get(https_index).status_code == status.HTTP_200_OK
    client.cookies.clear()
    assert client.get(https_index).status_code == status.HTTP_401_UNAUTHORIZED


def test_plugin_ui_file_with_nul_byte_is_404(probe, access_token, monkeypatch):
    # On Linux Path.resolve() raises ValueError for a NUL byte (Windows drops it); simulate that everywhere
    original_resolve = pathlib.Path.resolve

    def resolve(self, *args, **kwargs):
        if "\x00" in str(self):
            raise ValueError("embedded null byte")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "resolve", resolve)
    for path in ("%00", "app.js%00.html", "%00/../plugin.py"):
        response = client.get(f"/api/plugins/probe/ui/{path}", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_404_NOT_FOUND, path
    assert client.get("/api/plugins/probe/ui/app.js", headers=auth_headers(access_token)).status_code == 200


@pytest.mark.parametrize(
    ("url", "headers", "secure"),
    [
        # TLS ended by a proxy that sends no X-Forwarded-* headers: the panel sees plain http
        ("http://panel.example.com/api/plugins/probe/ui-session", {}, True),
        ("https://panel.example.com/api/plugins/probe/ui-session", {}, True),
        ("http://localhost/api/plugins/probe/ui-session", {}, False),
        ("http://127.0.0.1/api/plugins/probe/ui-session", {}, False),
        ("http://testserver/api/plugins/probe/ui-session", {"Host": "[::1]:8000"}, False),
        ("http://localhost/api/plugins/probe/ui-session", {"X-Forwarded-Proto": "https"}, True),
    ],
)
def test_plugin_ui_cookie_is_secure_except_plain_localhost(probe, access_token, url, headers, secure):
    response = client.post(url, headers={**auth_headers(access_token), **headers})
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert ("Secure" in response.headers["set-cookie"]) is secure


UNPROTECTED_ROUTES = {
    "raw": """
from starlette.responses import PlainTextResponse


def setup(ctx):
    async def raw(request):
        return PlainTextResponse("raw")

    ctx.router.add_route("/raw", raw)
    ctx.job(lambda: None, seconds=60)
""",
    "decorated": """
from starlette.responses import PlainTextResponse


def setup(ctx):
    @ctx.router.route("/raw")
    async def raw(request):
        return PlainTextResponse("raw")
""",
    "socket": """
def setup(ctx):
    @ctx.router.websocket("/raw")
    async def raw(websocket):
        await websocket.accept()
        await websocket.send_text("raw")
        await websocket.close()
""",
    "mounted": """
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route


async def raw(request):
    return PlainTextResponse("raw")


def setup(ctx):
    ctx.router.mount("/raw", Starlette(routes=[Route("/", raw)]))
""",
    "nested": """
from fastapi import APIRouter
from starlette.responses import PlainTextResponse


def setup(ctx):
    sub = APIRouter()

    async def raw(request):
        return PlainTextResponse("raw")

    sub.add_route("/raw", raw)
    ctx.router.include_router(sub)
""",
}

SUB_ROUTER = """
from fastapi import APIRouter


def setup(ctx):
    sub = APIRouter()

    @sub.get("/raw")
    async def raw():
        return {"ok": True}

    ctx.router.include_router(sub, prefix="/sub")
"""

ROUTE_AND_JOB = """
def setup(ctx):
    @ctx.router.get("/hello")
    async def hello():
        return {"ok": True}

    ctx.job(lambda: None, cron=CRON)
"""


@pytest.fixture
def activate_plugins(tmp_path):
    """Load fixture plugins and activate them the way ``init_plugins`` does."""
    reset_plugins()
    routes_before = len(app.router.routes)

    def load(plugins: dict[str, str], *, runs_scheduler: bool = False):
        for plugin_id, code in plugins.items():
            make_plugin(tmp_path, plugin_id, code)
        manager.load_all(tmp_path, list(plugins), runs_panel=True, runs_scheduler=runs_scheduler)
        manager.activate_all(app)
        return registry.records

    yield load
    for job in scheduler.get_jobs():
        if job.id.startswith("plugin:"):
            scheduler.remove_job(job.id)
    del app.router.routes[routes_before:]
    app.router._mark_routes_changed()
    reset_plugins()


def test_plugin_routes_without_panel_auth_are_refused(activate_plugins, access_token):
    records = activate_plugins({**UNPROTECTED_ROUTES, "subrouter": SUB_ROUTER}, runs_scheduler=True)

    for plugin_id in UNPROTECTED_ROUTES:
        assert records[plugin_id].status == "failed", plugin_id
        assert "would bypass panel auth" in records[plugin_id].error, plugin_id
        assert records[plugin_id].context is None
        for path in (f"/api/plugins/{plugin_id}/raw", f"/api/plugins/{plugin_id}/raw/"):
            assert client.get(path).status_code == status.HTTP_404_NOT_FOUND, path
            assert client.get(path, headers=auth_headers(access_token)).status_code == 404, path
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/plugins/socket/raw") as websocket:
        websocket.receive_text()
    # Refused before its jobs were scheduled
    assert not [job.id for job in scheduler.get_jobs() if job.id.startswith("plugin:raw:")]

    # Sub-routers made of FastAPI routes are fine and stay admin-only
    assert records["subrouter"].status == "loaded"
    assert client.get("/api/plugins/subrouter/sub/raw").status_code == status.HTTP_401_UNAUTHORIZED
    assert client.get("/api/plugins/subrouter/sub/raw", headers=auth_headers(access_token)).json() == {"ok": True}


def test_plugin_with_invalid_cron_fails_without_routes(activate_plugins, access_token):
    records = activate_plugins({"badcron": ROUTE_AND_JOB.replace("CRON", '"61 * * * *"')}, runs_scheduler=True)
    assert records["badcron"].status == "failed"
    assert client.get("/api/plugins/badcron/hello", headers=auth_headers(access_token)).status_code == 404
    assert not [job.id for job in scheduler.get_jobs() if job.id.startswith("plugin:badcron:")]
    # Refused at setup time by ctx.job(), with a message naming the call
    assert "ctx.job(cron='61 * * * *') is not a valid crontab" in records["badcron"].error


def test_plugin_whose_jobs_fail_to_register_mounts_no_routes(activate_plugins, access_token, monkeypatch):
    def failing_register_jobs(ctx):
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(manager, "register_jobs", failing_register_jobs)
    records = activate_plugins({"nojobs": ROUTE_AND_JOB.replace("CRON", '"0 9 * * *"')}, runs_scheduler=True)
    assert records["nojobs"].status == "failed"
    assert records["nojobs"].error == "scheduler unavailable"
    assert client.get("/api/plugins/nojobs/hello", headers=auth_headers(access_token)).status_code == 404


def test_plugin_sdk_is_served(probe):
    response = client.get("/api/plugins/sdk.js")
    assert response.status_code == status.HTTP_200_OK
    assert "pasarguard:ready" in response.text
    assert "javascript" in response.headers["content-type"]
