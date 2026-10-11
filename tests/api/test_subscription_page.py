"""Admin-controlled values must not break out of the markup of subscription pages and links."""

import asyncio

from fastapi import status
from sqlalchemy import update

from app.db.models import ProxyHost
from tests.api import TestSession, client
from tests.api.helpers import (
    auth_headers,
    create_core,
    create_group,
    create_user,
    delete_core,
    delete_group,
    delete_user,
    get_inbounds,
    unique_name,
)

BROWSER_HEADERS = {"Accept": "text/html", "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/147.0"}
PAYLOAD = '"><img src=x onerror="window.__xss=1">'


def _create_host(access_token: str, inbound: str, address: str):
    return client.post(
        "/api/host",
        headers=auth_headers(access_token),
        json={
            "remark": unique_name("sub_page_host"),
            "address": [address],
            "port": 443,
            "inbound_tag": inbound,
            "priority": 1,
        },
    )


def test_host_address_rejects_markup_characters(access_token):
    core = create_core(access_token)
    inbound = get_inbounds(access_token)[0]
    created: list[int] = []
    try:
        for address in (PAYLOAD, "a'b.example.com", 'a"b.example.com', "a b.example.com", "a`b", "a\\b", "<x>"):
            response = _create_host(access_token, inbound, address)
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, (address, response.text)

        for address in ("example.com", "*.example.com", "{SERVER_IP}", "[2001:db8::1]", "{USERNAME}.example.com"):
            response = _create_host(access_token, inbound, address)
            assert response.status_code == status.HTTP_201_CREATED, (address, response.text)
            created.append(response.json()["id"])
    finally:
        for host_id in created:
            client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_stored_markup_address_is_left_out_of_subscriptions(access_token):
    core = create_core(access_token)
    inbound = next(tag for tag in get_inbounds(access_token) if "VLESS" in tag.upper())
    group = create_group(access_token, name=unique_name("sub_page_group"), inbound_tags=[inbound])
    bad = _create_host(access_token, inbound, "bad.example.com").json()
    good = _create_host(access_token, inbound, "good.example.com").json()
    user = create_user(access_token, group_ids=[group["id"]], payload={"username": unique_name("sub_page_user")})

    async def plant_markup_address():
        # A row saved before address validation existed.
        async with TestSession() as session:
            await session.execute(update(ProxyHost).where(ProxyHost.id == bad["id"]).values(address={PAYLOAD}))
            await session.commit()

    asyncio.run(plant_markup_address())
    try:
        # A bulk save reloads every host from the database into the host cache.
        reload = client.put("/api/hosts", headers=auth_headers(access_token), json=[good])
        assert reload.status_code == status.HTTP_200_OK, reload.text

        page = client.get(user["subscription_url"], headers=BROWSER_HEADERS)
        assert page.status_code == status.HTTP_200_OK
        assert "good.example.com" in page.text
        assert "window.__xss" not in page.text
        assert 'onclick="copyLink(this.dataset.link, this)"' in page.text
        assert "copyLink('" not in page.text

        links = client.get(f"{user['subscription_url']}/links")
        assert links.status_code == status.HTTP_200_OK
        assert "good.example.com" in links.text
        assert "window.__xss" not in links.text
    finally:
        delete_user(access_token, user["username"])
        for host in (bad, good):
            client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_hysteria_auth_is_percent_encoded_in_links(access_token):
    core = create_core(access_token)
    inbound = "hy2"
    assert inbound in get_inbounds(access_token)
    group = create_group(access_token, name=unique_name("hy2_group"), inbound_tags=[inbound])
    host = _create_host(access_token, inbound, "hy.example.com").json()
    user = create_user(
        access_token,
        group_ids=[group["id"]],
        payload={"username": unique_name("hy2_user"), "proxy_settings": {"hysteria": {"auth": "a'b\"c<d> e"}}},
    )
    try:
        links = client.get(f"{user['subscription_url']}/links")
        assert links.status_code == status.HTTP_200_OK
        hysteria_links = [line for line in links.text.splitlines() if line.startswith("hysteria2://")]
        assert hysteria_links, links.text
        assert hysteria_links[0].startswith("hysteria2://a%27b%22c%3Cd%3E%20e@hy.example.com:")
    finally:
        delete_user(access_token, user["username"])
        client.delete(f"/api/host/{host['id']}", headers=auth_headers(access_token))
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])
