"""Settings saved before the current input checks must keep loading; only new input is held to them."""

import asyncio
import copy
import time
import tracemalloc
from unittest.mock import AsyncMock

import pytest
from fastapi import status
from sqlalchemy import select, update

from app.db.models import Settings
from app.models.settings import SettingsSchema, Subscription
from app.settings import refresh_caches, subscription_settings
from tests.api import TestSession, client
from tests.api.helpers import auth_headers, create_user, delete_user, unique_name

BROWSER_HEADERS = {"Accept": "text/html", "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/147.0"}
DATA_ICON = "data:image/png;base64,iVBORw0KGgo="


def _with_stored_bad_values(subscription: dict) -> dict:
    """Values accepted by earlier versions and rejected by the new checks."""
    stored = copy.deepcopy(subscription)
    stored["announce"] = "{USERNAME:>9999}"
    stored["profile_title"] = "{USERNAME:>999999999}"
    stored["announce_url"] = "javascript:alert(1)"
    stored["custom_variables"] = [{"key": "WIDE", "value": "{USERNAME:>999999999}"}]
    stored["rules"] = [
        {"pattern": "a" * 600, "target": "links", "response_headers": {}},
        {"pattern": "(a+)+$", "target": "links", "response_headers": {}},
        {"pattern": "(", "target": "links", "response_headers": {}},
        *stored.get("rules", []),
    ]
    stored["applications"] = [
        {
            "name": "Old",
            "icon_url": DATA_ICON,
            "import_url": "happ://add/{url}#{url.x}",
            "description": {},
            "recommended": False,
            "show_when_hwid_enabled": True,
            "platform": "android",
            "download_links": [
                {"name": "bad", "url": "javascript:alert(1)", "language": "en"},
                {"name": "good", "url": "https://example.com/app.apk", "language": "en"},
            ],
        }
    ]
    return stored


async def _read_db_subscription() -> dict:
    async with TestSession() as session:
        return (await session.execute(select(Settings.subscription))).scalar_one()


async def _write_db_subscription(subscription: dict) -> None:
    async with TestSession() as session:
        await session.execute(update(Settings).values(subscription=subscription))
        await session.commit()


@pytest.fixture
def stored_bad_settings():
    original = asyncio.run(_read_db_subscription())
    stored = _with_stored_bad_values(original)
    asyncio.run(_write_db_subscription(stored))
    try:
        yield original, stored
    finally:
        asyncio.run(_write_db_subscription(original))


def test_stored_values_load_through_the_real_validators(mock_settings):
    stored = _with_stored_bad_values(mock_settings["subscription"])

    loaded = Subscription.model_validate(stored)
    assert loaded.applications[0].icon_url == DATA_ICON
    assert loaded.applications[0].import_url == "happ://add/{url}#{url.x}"
    assert loaded.announce == "{USERNAME:>9999}"
    assert loaded.rules[0].pattern == "a" * 600

    SettingsSchema.model_validate(Settings(**{**mock_settings, "subscription": stored}))


def test_subscription_settings_cache_loads_stored_values(monkeypatch, mock_settings):
    stored = _with_stored_bad_values(mock_settings["subscription"])
    monkeypatch.setattr(
        "app.settings.get_settings", AsyncMock(return_value=Settings(**{**mock_settings, "subscription": stored}))
    )

    async def load():
        await refresh_caches()
        try:
            return await subscription_settings()
        finally:
            await refresh_caches()

    assert asyncio.run(load()).announce == "{USERNAME:>9999}"


def test_subscription_page_and_apps_survive_stored_values(access_token, monkeypatch, mock_settings):
    stored = _with_stored_bad_values(mock_settings["subscription"])
    monkeypatch.setattr(
        "app.settings.get_settings", AsyncMock(return_value=Settings(**{**mock_settings, "subscription": stored}))
    )
    asyncio.run(refresh_caches())
    user = create_user(access_token, payload={"username": unique_name("stored_settings_user")})
    try:
        tracemalloc.start()
        started = time.perf_counter()
        page = client.get(user["subscription_url"], headers=BROWSER_HEADERS)
        # A client request renders the profile title, announce and custom variables into headers
        info = client.get(user["subscription_url"], headers={"User-Agent": "v2rayN/7.0"})
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        assert page.status_code == status.HTTP_200_OK
        assert elapsed < 1
        assert peak < 100 * 1024 * 1024
        assert user["username"] in page.text
        assert "javascript:" not in page.text

        apps = client.get(f"{user['subscription_url']}/apps")
        assert apps.status_code == status.HTTP_200_OK
        app = apps.json()[0]
        assert app["icon_url"] == DATA_ICON
        assert app["import_url"] == "happ://add/{url}#{url.x}"
        assert [link["name"] for link in app["download_links"]] == ["good"]

        assert info.status_code == status.HTTP_200_OK
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        delete_user(access_token, user["username"])
        asyncio.run(refresh_caches())


def test_settings_api_loads_stored_values_and_rejects_them_as_input(access_token, stored_bad_settings):
    original, stored = stored_bad_settings

    response = client.get("/api/settings", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()["subscription"]["announce"] == "{USERNAME:>9999}"
    assert client.get("/api/settings/general", headers=auth_headers(access_token)).status_code == status.HTTP_200_OK

    rejected = client.put("/api/settings", headers=auth_headers(access_token), json={"subscription": stored})
    assert rejected.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, rejected.text

    for field, value in (
        ("announce", "{USERNAME:>9999}"),
        ("import_url", "happ://add/{url}#{url.x}"),
        ("pattern", "a" * 600),
    ):
        only_one = copy.deepcopy(original)
        if field == "announce":
            only_one["announce"] = value
        elif field == "import_url":
            only_one["applications"] = copy.deepcopy(stored["applications"])
            only_one["applications"][0]["import_url"] = value
            only_one["applications"][0]["download_links"] = []
        else:
            only_one["rules"] = [{"pattern": value, "target": "links", "response_headers": {}}]
        bad = client.put("/api/settings", headers=auth_headers(access_token), json={"subscription": only_one})
        assert bad.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, (field, bad.text)

    # Another section saves while the stored subscription is still the old one
    general = response.json()["general"]
    saved = client.put(
        "/api/settings",
        headers=auth_headers(access_token),
        json={"general": {"default_method": general["default_method"]}},
    )
    assert saved.status_code == status.HTTP_200_OK, saved.text

    fixed = copy.deepcopy(original)
    fixed["applications"] = copy.deepcopy(stored["applications"])
    fixed["applications"][0]["import_url"] = "happ://add/{url}"
    fixed["applications"][0]["download_links"] = [stored["applications"][0]["download_links"][1]]
    saved = client.put("/api/settings", headers=auth_headers(access_token), json={"subscription": fixed})
    assert saved.status_code == status.HTTP_200_OK, saved.text
    # data: icons stay allowed on input: they only end up in <img src>
    assert saved.json()["subscription"]["applications"][0]["icon_url"] == DATA_ICON
