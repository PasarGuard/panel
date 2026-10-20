"""Telegram proxy links appear on the subscription page and the dashboard, never in client formats."""

import base64
from uuid import uuid4

import pytest
from fastapi import status

from app.subscription.config_cache import clear_sub_config_cache
from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_group,
    create_mtproto_core,
    create_user,
    delete_core,
    delete_group,
    delete_user,
    strip_mtproto_settings,
    unique_name,
)

BROWSER_HEADERS = {"Accept": "text/html", "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/147.0"}
TLS_DOMAIN = "www.example.org"


@pytest.fixture
def mtproto_setup(access_token):
    headers = auth_headers(access_token)
    tag = unique_name("mtp_in")
    core = create_mtproto_core(access_token, tag=tag)
    response = client.post(
        "/api/host",
        headers=headers,
        json={
            "remark": unique_name("mtp_host"),
            "address": ["mtp.example.net"],
            "port": 8443,
            "inbound_tag": tag,
            "priority": 1,
        },
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    host = response.json()
    group = create_group(access_token, inbound_tags=[tag])
    user = create_user(access_token, group_ids=[group["id"]])
    try:
        yield user, group
    finally:
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        client.delete(f"/api/host/{host['id']}", headers=headers)
        delete_core(access_token, core["id"])


def _raw_links(user: dict) -> list[str]:
    response = client.get(f"{user['subscription_url']}/raw")
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()["body"]["links"]


def _expected_link(secret: str) -> str:
    return f"tg://proxy?server=mtp.example.net&port=8443&secret=ee{secret}{TLS_DOMAIN.encode().hex()}"


def test_page_raw_and_admin_links_show_telegram_link(access_token, mtproto_setup):
    user, _ = mtproto_setup
    expected = _expected_link(user["proxy_settings"]["mtproto"]["secret"])

    assert expected in _raw_links(user)

    page = client.get(user["subscription_url"], headers=BROWSER_HEADERS)
    assert page.status_code == status.HTTP_200_OK
    assert "tg://proxy?server=mtp.example.net" in page.text

    admin_links = client.get(f"/api/user/{user['id']}/subscription/links", headers=auth_headers(access_token))
    assert admin_links.status_code == status.HTTP_200_OK, admin_links.text
    assert expected in admin_links.text.splitlines()


def test_client_formats_never_carry_telegram_links(mtproto_setup):
    user, _ = mtproto_setup
    for client_type in ("links", "xray", "sing_box", "clash_meta"):
        response = client.get(f"{user['subscription_url']}/{client_type}")
        assert response.status_code == status.HTTP_200_OK, (client_type, response.text)
        assert "tg://" not in response.text, client_type
        assert "t.me/proxy" not in response.text, client_type

    response = client.get(f"{user['subscription_url']}/links_base64")
    assert response.status_code == status.HTTP_200_OK, response.text
    assert "tg://" not in base64.b64decode(response.text).decode()


def test_user_without_secret_gets_no_telegram_link(access_token, mtproto_setup):
    _, group = mtproto_setup
    user = create_user(access_token, group_ids=[group["id"]])
    try:
        strip_mtproto_settings(user["id"])
        # The sub-config cache key ignores proxy settings: clear it so each fetch is a real render.
        clear_sub_config_cache()
        first = _raw_links(user)
        clear_sub_config_cache()
        second = _raw_links(user)
        # A read path that invented a secret would give a different random link on each render.
        assert first == second
        for link in first:
            assert "tg://" not in link
            assert "t.me/proxy" not in link

        # Positive control: once a secret is assigned, the same user gets its Telegram link.
        secret = uuid4().hex
        response = client.put(
            f"/api/user/by-id/{user['id']}",
            headers=auth_headers(access_token),
            json={"proxy_settings": {"mtproto": {"secret": secret}}},
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        clear_sub_config_cache()
        assert _expected_link(secret) in _raw_links(user)
    finally:
        delete_user(access_token, user["username"])
