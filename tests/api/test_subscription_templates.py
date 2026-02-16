import json
import os
import tempfile

import pytest
from fastapi import status

from tests.api import client
from tests.api.helpers import auth_headers, create_core, delete_core, get_inbounds, unique_name


@pytest.fixture()
def custom_templates_dir(monkeypatch):
    """Create a temporary custom templates directory with a sample xray template."""
    with tempfile.TemporaryDirectory() as tmpdir:
        xray_dir = os.path.join(tmpdir, "xray")
        os.makedirs(xray_dir)

        template = {
            "log": {"loglevel": "warning"},
            "inbounds": [],
            "outbounds": [],
            "dns": {"servers": ["1.1.1.1"]},
            "routing": {"domainStrategy": "AsIs", "rules": []},
        }
        with open(os.path.join(xray_dir, "custom.json"), "w") as f:
            json.dump(template, f)

        with open(os.path.join(xray_dir, "another.json"), "w") as f:
            json.dump(template, f)

        monkeypatch.setattr("config.CUSTOM_TEMPLATES_DIRECTORY", tmpdir)
        monkeypatch.setattr("app.templates.CUSTOM_TEMPLATES_DIRECTORY", tmpdir)
        monkeypatch.setattr("app.templates.template_directories", [tmpdir, "app/templates"])

        import app.templates

        app.templates.env = app.templates.jinja2.Environment(
            loader=app.templates.jinja2.FileSystemLoader([tmpdir, "app/templates"])
        )
        app.templates.env.filters.update(app.templates.CUSTOM_FILTERS)

        yield tmpdir


@pytest.fixture()
def no_custom_templates_dir(monkeypatch):
    """Ensure CUSTOM_TEMPLATES_DIRECTORY is not set."""
    monkeypatch.setattr("config.CUSTOM_TEMPLATES_DIRECTORY", None)
    monkeypatch.setattr("app.templates.CUSTOM_TEMPLATES_DIRECTORY", None)
    yield


# --- GET /api/host/subscription-templates ---


def test_subscription_templates_list(access_token, custom_templates_dir):
    """List endpoint returns custom templates grouped by format."""
    response = client.get("/api/host/subscription-templates", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "xray" in data
    assert "clash" in data
    assert "singbox" in data

    assert "xray/custom.json" in data["xray"]
    assert "xray/another.json" in data["xray"]


def test_subscription_templates_list_excludes_defaults(access_token, custom_templates_dir):
    """List endpoint only returns custom templates, not built-in defaults."""
    response = client.get("/api/host/subscription-templates", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "xray/default.json" not in data["xray"]


def test_subscription_templates_list_empty_without_custom_dir(access_token, no_custom_templates_dir):
    """List endpoint returns empty lists when no custom dir is configured."""
    response = client.get("/api/host/subscription-templates", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["xray"] == []
    assert data["clash"] == []
    assert data["singbox"] == []


def test_subscription_templates_list_requires_auth():
    """List endpoint requires authentication."""
    response = client.get("/api/host/subscription-templates")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# --- Host CRUD with subscription_templates ---


def test_host_create_with_subscription_template(access_token, custom_templates_dir):
    """Host creation accepts a valid custom subscription template."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds

    try:
        payload = {
            "remark": unique_name("host_tpl"),
            "address": ["127.0.0.1"],
            "port": 443,
            "inbound_tag": inbounds[0],
            "priority": 1,
            "subscription_templates": {"xray": "xray/custom.json"},
        }
        response = client.post("/api/host", headers=auth_headers(access_token), json=payload)
        assert response.status_code == status.HTTP_201_CREATED

        data = response.json()
        assert data["subscription_templates"] == {"xray": "xray/custom.json"}

        client.delete(f"/api/host/{data['id']}", headers=auth_headers(access_token))
    finally:
        delete_core(access_token, core["id"])


def test_host_create_with_null_subscription_template(access_token):
    """Host creation accepts null subscription_templates (uses global default)."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds

    try:
        payload = {
            "remark": unique_name("host_null_tpl"),
            "address": ["127.0.0.1"],
            "port": 443,
            "inbound_tag": inbounds[0],
            "priority": 1,
            "subscription_templates": None,
        }
        response = client.post("/api/host", headers=auth_headers(access_token), json=payload)
        assert response.status_code == status.HTTP_201_CREATED

        data = response.json()
        assert data["subscription_templates"] is None

        client.delete(f"/api/host/{data['id']}", headers=auth_headers(access_token))
    finally:
        delete_core(access_token, core["id"])


def test_host_create_with_invalid_subscription_template(access_token, custom_templates_dir):
    """Host creation rejects a non-existent subscription template."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds

    try:
        payload = {
            "remark": unique_name("host_bad_tpl"),
            "address": ["127.0.0.1"],
            "port": 443,
            "inbound_tag": inbounds[0],
            "priority": 1,
            "subscription_templates": {"xray": "xray/nonexistent.json"},
        }
        response = client.post("/api/host", headers=auth_headers(access_token), json=payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not available" in response.json()["detail"]
    finally:
        delete_core(access_token, core["id"])


def test_host_update_subscription_template(access_token, custom_templates_dir):
    """Host update can change the subscription template."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds

    try:
        create_payload = {
            "remark": unique_name("host_update_tpl"),
            "address": ["127.0.0.1"],
            "port": 443,
            "inbound_tag": inbounds[0],
            "priority": 1,
            "subscription_templates": None,
        }
        create_resp = client.post("/api/host", headers=auth_headers(access_token), json=create_payload)
        assert create_resp.status_code == status.HTTP_201_CREATED
        host_id = create_resp.json()["id"]

        update_payload = {
            "remark": create_payload["remark"],
            "address": ["127.0.0.1"],
            "port": 443,
            "inbound_tag": inbounds[0],
            "priority": 1,
            "subscription_templates": {"xray": "xray/another.json"},
        }
        update_resp = client.put(f"/api/host/{host_id}", headers=auth_headers(access_token), json=update_payload)
        assert update_resp.status_code == status.HTTP_200_OK
        assert update_resp.json()["subscription_templates"] == {"xray": "xray/another.json"}

        client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
    finally:
        delete_core(access_token, core["id"])


def test_host_update_clear_subscription_template(access_token, custom_templates_dir):
    """Host update can clear subscription template back to null."""
    core = create_core(access_token)
    inbounds = get_inbounds(access_token)
    assert inbounds

    try:
        create_payload = {
            "remark": unique_name("host_clear_tpl"),
            "address": ["127.0.0.1"],
            "port": 443,
            "inbound_tag": inbounds[0],
            "priority": 1,
            "subscription_templates": {"xray": "xray/custom.json"},
        }
        create_resp = client.post("/api/host", headers=auth_headers(access_token), json=create_payload)
        assert create_resp.status_code == status.HTTP_201_CREATED
        host_id = create_resp.json()["id"]
        assert create_resp.json()["subscription_templates"] == {"xray": "xray/custom.json"}

        update_payload = {
            "remark": create_payload["remark"],
            "address": ["127.0.0.1"],
            "port": 443,
            "inbound_tag": inbounds[0],
            "priority": 1,
            "subscription_templates": None,
        }
        update_resp = client.put(f"/api/host/{host_id}", headers=auth_headers(access_token), json=update_payload)
        assert update_resp.status_code == status.HTTP_200_OK
        assert update_resp.json()["subscription_templates"] is None

        client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
    finally:
        delete_core(access_token, core["id"])
