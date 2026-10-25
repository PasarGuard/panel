"""The example plugins in examples/plugins load and work."""

import asyncio
import sys
import time
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi import status

from app.plugins import events, manager, registry
from app.scheduler import scheduler
from app.subscription.config_cache import clear_sub_config_cache
from tests.api import GetTestDB, app, client
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
    unique_name,
)
from tests.plugin_helpers import reset_plugins

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples" / "plugins"


async def _always_claim(*_args, **_kwargs) -> bool:
    return True


@pytest.fixture
def examples(monkeypatch):
    reset_plugins()
    # The subscription cache is keyed by user id, and SQLite reuses ids of deleted users
    clear_sub_config_cache()
    monkeypatch.setattr("app.db.GetDB", GetTestDB)  # ctx.db() of the plugins
    # CI runs with 2 workers and NATS: both cross-worker claims run before the event and can wait for a NATS timeout
    monkeypatch.setattr("app.notification.claim_notification_slot", _always_claim)
    monkeypatch.setattr(events, "_claim", _always_claim)
    routes_before = len(app.router.routes)
    manager.load_all(EXAMPLES_DIR, ["expiring-report", "sub-banner"], runs_panel=True, runs_scheduler=True)
    for ctx in registry.active:
        manager.activate(app, ctx)
    # sub-banner has an async setup: it runs at startup
    asyncio.run(manager.finish_pending_setups(app))
    yield
    for job in scheduler.get_jobs():
        if job.id.startswith("plugin:"):
            scheduler.remove_job(job.id)
    del app.router.routes[routes_before:]
    app.router._mark_routes_changed()
    reset_plugins()
    clear_sub_config_cache()


def test_examples_load(examples, access_token):
    assert {plugin_id: record.status for plugin_id, record in registry.records.items()} == {
        "expiring-report": "loaded",
        "sub-banner": "loaded",
    }
    assert [job.id for job in scheduler.get_jobs() if job.id.startswith("plugin:expiring-report:")] == [
        "plugin:expiring-report:daily_report:0"
    ]
    plugins = client.get("/api/plugins", headers=auth_headers(access_token)).json()["plugins"]
    assert {p["id"]: p["has_ui"] for p in plugins} == {"expiring-report": True, "sub-banner": False}
    settings = client.get("/api/plugins/sub-banner/settings", headers=auth_headers(access_token)).json()
    assert settings["enabled"] is True and settings["default_plan"] == "Basic"


def test_expiring_report_lists_users(examples, access_token):
    soon = unique_name("expiring_soon")
    later = unique_name("expiring_later")
    now = datetime.now(UTC)
    create_user(access_token, payload={"username": soon, "expire": (now + timedelta(days=3)).isoformat()})
    create_user(access_token, payload={"username": later, "expire": (now + timedelta(days=60)).isoformat()})
    try:
        assert client.get("/api/plugins/expiring-report/users").status_code == status.HTTP_401_UNAUTHORIZED
        response = client.get("/api/plugins/expiring-report/users", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        names = [user["username"] for user in data["users"]]
        assert data["days"] == 7
        assert soon in names and later not in names

        wide = client.get("/api/plugins/expiring-report/users?days=90", headers=auth_headers(access_token)).json()
        assert later in [user["username"] for user in wide["users"]]

        # The report covers all users, so a sub-admin may not read it
        admin = create_admin(access_token)
        try:
            token = client.post(
                "/api/admin/token",
                data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
            ).json()["access_token"]
            sub_admin = client.get("/api/plugins/expiring-report/users", headers=auth_headers(token))
            assert sub_admin.status_code == status.HTTP_403_FORBIDDEN
        finally:
            delete_admin(access_token, admin["username"])

        ui = client.get("/api/plugins/expiring-report/ui/", headers=auth_headers(access_token))
        assert ui.status_code == status.HTTP_200_OK and "/api/plugins/sdk.js" in ui.text
    finally:
        delete_user(access_token, soon)
        delete_user(access_token, later)


def test_sub_banner_prepends_info_link(examples, access_token):
    username = unique_name("banner_user")
    expire = datetime.now(UTC) + timedelta(days=10, hours=1)
    user = create_user(access_token, payload={"username": username, "expire": expire.isoformat()})
    try:
        body = client.get(f"{user['subscription_url']}/links").text
        first_line = body.splitlines()[0]
        assert first_line.startswith("vless://00000000-0000-0000-0000-000000000000@127.0.0.1:1")
        assert first_line.endswith("#" + quote("⏳ 11 days left · Basic", safe=""))

        clash = client.get(f"{user['subscription_url']}/clash").text
        assert "00000000-0000-0000-0000-000000000000" not in clash
    finally:
        delete_user(access_token, username)


def test_sub_banner_plan_comes_from_memory_not_the_database(examples, access_token, monkeypatch):
    module = next(m for name, m in sys.modules.items() if name.endswith(".plugin") and hasattr(m, "groups_by_user"))
    core = create_core(access_token)
    group = create_group(access_token, name=unique_name("premium"))
    username = unique_name("banner_plan_user")
    try:
        saved = client.put(
            "/api/plugins/sub-banner/settings",
            headers=auth_headers(access_token),
            json={"plans": {group["name"]: "Premium"}},
        )
        assert saved.status_code == status.HTTP_200_OK
        user = create_user(access_token, username=username, group_ids=[group["id"]])
        # The user.created event fills the map in the background
        deadline = time.monotonic() + 5
        while module.groups_by_user.get(user["id"]) != [group["name"]] and time.monotonic() < deadline:
            time.sleep(0.05)
        assert module.groups_by_user.get(user["id"]) == [group["name"]]

        # Hooks swallow their own errors, so record every session the plugin opens instead of raising.
        # The background refresh (load_all) may legitimately open one; anything else came from a hook.
        ctx = registry.get_active("sub-banner")
        real_db = ctx.db
        hook_sessions = []

        def counting_db():
            callers = [frame.name for frame in traceback.extract_stack()]
            if "load_all" not in callers:
                hook_sessions.append(callers[-2])
            return real_db()

        monkeypatch.setattr(ctx, "db", counting_db)
        first_line = client.get(f"{user['subscription_url']}/links").text.splitlines()[0]
        assert first_line.endswith(quote("Premium", safe=""))
        assert hook_sessions == []
    finally:
        delete_user(access_token, username)
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])
