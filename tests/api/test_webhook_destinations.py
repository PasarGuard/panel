"""Saving webhook settings checks the destination; WEBHOOK_ALLOW_PRIVATE_DESTINATIONS lifts only the address check."""

from fastapi import status

from config import server_settings
from tests.api import client
from tests.api.helpers import auth_headers


def _webhook_section(url: str) -> dict:
    return {
        "enable": False,
        "webhooks": [{"url": url, "secret": "s"}],
        "days_left": [3],
        "usage_percent": [80],
        "timeout": 180,
        "recurrent": 3,
        "proxy_url": None,
    }


def test_private_webhook_save_follows_the_flag(access_token, monkeypatch):
    original = client.get("/api/settings", headers=auth_headers(access_token)).json()["webhook"]
    try:
        monkeypatch.setattr(server_settings, "webhook_allow_private_destinations", False)
        refused = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"webhook": _webhook_section("http://10.0.0.5:8080/hook")},
        )
        assert refused.status_code == status.HTTP_400_BAD_REQUEST
        assert "WEBHOOK_ALLOW_PRIVATE_DESTINATIONS" in refused.json()["detail"]

        monkeypatch.setattr(server_settings, "webhook_allow_private_destinations", True)
        allowed = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"webhook": _webhook_section("http://10.0.0.5:8080/hook")},
        )
        assert allowed.status_code == status.HTTP_200_OK, allowed.text
        assert allowed.json()["webhook"]["webhooks"][0]["url"] == "http://10.0.0.5:8080/hook"

        # The flag lifts the address check only: the destination still has to be http(s).
        not_http = client.put(
            "/api/settings",
            headers=auth_headers(access_token),
            json={"webhook": _webhook_section("ftp://10.0.0.5/hook")},
        )
        assert not_http.status_code == status.HTTP_400_BAD_REQUEST, not_http.text
    finally:
        monkeypatch.setattr(server_settings, "webhook_allow_private_destinations", True)
        client.put("/api/settings", headers=auth_headers(access_token), json={"webhook": original})
