"""The example plugins in examples/plugins load and work."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi import status

from app.plugins import manager, registry
from app.scheduler import scheduler
from tests.api import GetTestDB, app, client
from tests.api.helpers import auth_headers, create_user, delete_user, unique_name
from tests.plugin_helpers import reset_plugins

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples" / "plugins"


@pytest.fixture
def examples(monkeypatch):
    reset_plugins()
    monkeypatch.setattr("app.db.GetDB", GetTestDB)  # ctx.db() of the plugins
    routes_before = len(app.router.routes)
    manager.load_all(EXAMPLES_DIR, ["expiring-report", "sub-banner"], runs_panel=True, runs_scheduler=True)
    for ctx in registry.active:
        manager.activate(app, ctx)
    yield
    for job in scheduler.get_jobs():
        if job.id.startswith("plugin:"):
            scheduler.remove_job(job.id)
    del app.router.routes[routes_before:]
    app.router._mark_routes_changed()
    reset_plugins()


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
