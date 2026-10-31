"""Core create/edit through the API: TLS files are confined to TLS_FILES_ALLOWED_DIRS."""

import pytest
from fastapi import status

from app.core import xray
from tests.api import client
from tests.api.helpers import auth_headers, create_core, delete_core, unique_name
from tests.test_xray_tls_fallback import _config, _parent_inbound, _write_self_signed

SHADOW = "root:$6$secret-hash:19000:0:99999:7:::\n"


@pytest.fixture
def tls_dirs(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    monkeypatch.setattr(xray.server_settings, "tls_files_allowed_dirs", str(allowed))
    monkeypatch.setattr(xray.server_settings, "ssl_keyfile", None)
    return allowed, outside


def _tls_config(cert_path: str, key_path: str) -> dict:
    return _config([_parent_inbound([{"certificateFile": cert_path, "keyFile": key_path}], [])])


def _payload(config: dict) -> dict:
    return {
        "config": config,
        "name": unique_name("tls_core"),
        "type": "xray",
        "exclude_inbound_tags": [],
        "fallbacks_inbound_tags": [],
    }


def test_create_core_with_key_file_outside_allowed_dirs_is_refused(access_token, tls_dirs):
    allowed, outside = tls_dirs
    cert_path, _ = _write_self_signed(allowed)
    shadow = outside / "shadow"
    shadow.write_text(SHADOW)

    response = client.post(
        "/api/core", headers=auth_headers(access_token), json=_payload(_tls_config(cert_path, str(shadow)))
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "outside the directories allowed" in response.text
    assert "secret-hash" not in response.text


def test_modify_core_with_key_file_outside_allowed_dirs_is_refused(access_token, tls_dirs):
    allowed, outside = tls_dirs
    cert_path, _ = _write_self_signed(allowed)
    shadow = outside / "shadow"
    shadow.write_text(SHADOW)
    core = create_core(access_token)

    response = client.put(
        f"/api/core/{core['id']}",
        headers=auth_headers(access_token),
        json=_payload(_tls_config(cert_path, str(shadow))),
        params={"restart_nodes": False},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "outside the directories allowed" in response.text
    assert "secret-hash" not in response.text
    delete_core(access_token, core["id"])


def test_create_core_with_non_key_file_inside_allowed_dir_is_refused(access_token, tls_dirs):
    allowed, _ = tls_dirs
    cert_path, _ = _write_self_signed(allowed)
    not_a_key = allowed / "notes.txt"
    not_a_key.write_text(SHADOW)

    response = client.post(
        "/api/core", headers=auth_headers(access_token), json=_payload(_tls_config(cert_path, str(not_a_key)))
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "not an unencrypted PEM private key" in response.text
    assert "secret-hash" not in response.text


def test_create_core_reusing_panel_https_key_is_accepted(access_token, tls_dirs, monkeypatch):
    allowed, _ = tls_dirs
    cert_path, key_path = _write_self_signed(allowed)
    monkeypatch.setattr(xray.server_settings, "ssl_keyfile", key_path)

    response = client.post(
        "/api/core", headers=auth_headers(access_token), json=_payload(_tls_config(cert_path, key_path))
    )

    assert response.status_code == status.HTTP_201_CREATED, response.text
    delete_core(access_token, response.json()["id"])
