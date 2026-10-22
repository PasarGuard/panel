"""Host fields formatted with the subscription variables: rejected on save when they cannot render, tolerated if stored."""

import asyncio
from collections import defaultdict

import pytest
from fastapi import status

from app.core.hosts import host_manager
from app.db.crud.host import get_host_by_id, get_hosts
from app.subscription import config_cache
from app.subscription.share import _format_dynamic_value
from tests.api import GetTestDB, client
from tests.api.helpers import (
    auth_headers,
    create_core,
    create_group,
    create_user,
    delete_core,
    delete_group,
    delete_user,
    unique_name,
)

INBOUND_TAG = "VLESS WebSocket TEST"

UNRENDERABLE_VALUES = [
    ("path", "/ws{"),
    ("path", "/ws/{0}"),
    ("path", "/ws/{}"),
    ("sni", ["cdn{.example.com"]),
    ("host", ["{USERNAME.missing}.example.com"]),
    ("address", ["edge}.example.com"]),
    ("remark", "{USERNAME[0]}"),
    ("remark", "{USERNAME.upper}"),
]

# str.format_map builds the padded result first, so a width like 1000000000 would allocate a gigabyte on every render
OVERSIZED_FORMAT_VALUES = [
    ("path", "/ws/{USERNAME:>100000}"),
    ("sni", ["{USERNAME:.100000}.example.com"]),
    ("host", ["{USERNAME:0300}.example.com"]),
    ("address", ["{SERVER_IP:^257}"]),
    ("remark", "{USERNAME:^100000}"),
]

# !r and !a wrap the value in quotes: an address with quotes is skipped as unsafe, the other fields break
QUOTING_CONVERSION_VALUES = [
    ("address", ["{SERVER_IP!r}"]),
    ("sni", ["{USERNAME!r}.example.com"]),
    ("host", ["{USERNAME!a}.example.com"]),
    ("path", "/ws/{USERNAME!a}"),
]


def _host_payload(**overrides) -> dict:
    return {
        "remark": unique_name("fmt"),
        "address": ["198.51.100.9"],
        "inbound_tag": INBOUND_TAG,
        "priority": 1,
    } | overrides


@pytest.mark.parametrize("field,value", UNRENDERABLE_VALUES + OVERSIZED_FORMAT_VALUES + QUOTING_CONVERSION_VALUES)
def test_host_with_unrenderable_format_field_is_rejected(access_token, field, value):
    headers = auth_headers(access_token)
    core = create_core(access_token)
    host_ids = []
    try:
        response = client.post("/api/host", headers=headers, json=_host_payload(**{field: value}))
        if response.status_code == status.HTTP_201_CREATED:
            host_ids.append(response.json()["id"])
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text

        payload = _host_payload()
        response = client.post("/api/host", headers=headers, json=payload)
        assert response.status_code == status.HTTP_201_CREATED, response.text
        host_ids.append(host_id := response.json()["id"])

        response = client.put(f"/api/host/{host_id}", headers=headers, json=payload | {field: value})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text

        response = client.put("/api/hosts", headers=headers, json=[payload | {"id": host_id, field: value}])
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
    finally:
        for host_id in host_ids:
            client.delete(f"/api/host/{host_id}", headers=headers)
        delete_core(access_token, core["id"])


def test_bulk_host_save_names_the_unrenderable_value(access_token):
    """The bulk save (dashboard priority reorder) must say which value it rejected."""
    headers = auth_headers(access_token)
    core = create_core(access_token)
    host_ids = []
    try:
        for _ in range(2):
            response = client.post("/api/host", headers=headers, json=_host_payload())
            assert response.status_code == status.HTTP_201_CREATED, response.text
            host_ids.append(response.json()["id"])
        hosts = [_host_payload(id=host_ids[0]), _host_payload(id=host_ids[1], path="/legacy{")]

        response = client.put("/api/hosts", headers=headers, json=hosts)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, response.text
        assert "/legacy{" in response.json()["detail"]["path"]
    finally:
        for host_id in host_ids:
            client.delete(f"/api/host/{host_id}", headers=headers)
        delete_core(access_token, core["id"])


def test_host_with_format_variables_is_accepted(access_token):
    headers = auth_headers(access_token)
    core = create_core(access_token)
    payload = _host_payload(
        remark="{USERNAME:>256} {USERNAME!r} {{literal}} {CUSTOM_VAR}",
        address=["{SERVER_IP!s}"],
        sni=["{USERNAME}.example.com"],
        host=["cdn.example.com"],
        path="/ws/{USERNAME}?ed={DAYS_LEFT:>4}",
    )
    try:
        response = client.post("/api/host", headers=headers, json=payload)
        assert response.status_code == status.HTTP_201_CREATED, response.text
        client.delete(f"/api/host/{response.json()['id']}", headers=headers)
    finally:
        delete_core(access_token, core["id"])


async def _store_unvalidated_fields(host_id: int, **fields) -> None:
    """Write host fields straight to the database, like rows saved before save time validation existed."""
    async with GetTestDB() as db:
        db_host = await get_host_by_id(db, host_id)
        for name, value in fields.items():
            setattr(db_host, name, value)
        await db.commit()
        await host_manager.add_hosts(db, await get_hosts(db=db))


def test_subscription_survives_stored_host_with_unrenderable_fields(access_token):
    headers = auth_headers(access_token)
    core = create_core(access_token)
    group = create_group(access_token, inbound_tags=[INBOUND_TAG])
    user = create_user(access_token, group_ids=[group["id"]])
    host_ids = []
    try:
        for address in ("good.example.com", "broken.example.com"):
            response = client.post("/api/host", headers=headers, json=_host_payload(address=[address], path="/ws"))
            assert response.status_code == status.HTTP_201_CREATED, response.text
            host_ids.append(response.json()["id"])
        asyncio.run(
            _store_unvalidated_fields(
                host_ids[1],
                remark="{USERNAME[99]}",
                address={"edge}.example.com"},
                sni={"cdn{.example.com"},
                host={"{USERNAME.missing}.example.com"},
                path="/ws/{0}",
            )
        )

        for client_type in ("links", "links_base64", "xray", "sing_box", "clash", "clash_meta"):
            config_cache.clear_sub_config_cache()
            response = client.get(f"{user['subscription_url']}/{client_type}")
            assert response.status_code == status.HTTP_200_OK, (client_type, response.text)
        config_cache.clear_sub_config_cache()
        # The healthy host is still served next to the broken one
        assert "good.example.com" in client.get(f"{user['subscription_url']}/links").text
    finally:
        for host_id in host_ids:
            client.delete(f"/api/host/{host_id}", headers=headers)
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_format_dynamic_value_keeps_values_the_variables_cannot_fill():
    variables = defaultdict(lambda: "<missing>", {"USERNAME": "bob"})
    request = {"headers": {"Host": ["{USERNAME}.example.com", "{USERNAME.x}", "{USERNAME[9]}", "/ws{", "{0}"]}}

    assert _format_dynamic_value(request, variables) == {
        "headers": {"Host": ["bob.example.com", "{USERNAME.x}", "{USERNAME[9]}", "/ws{", "{0}"]}
    }


def test_format_dynamic_value_does_not_pad_oversized_widths():
    """A stored oversized width (saved before the check) is kept as raw text instead of being padded on every render."""
    variables = defaultdict(lambda: "<missing>", {"USERNAME": "bob", "PAD": "100000"})
    oversized = ["{USERNAME:>100000}", "{USERNAME:.100000}", "{USERNAME:>{PAD}}"]

    assert _format_dynamic_value(oversized, variables) == oversized
    assert _format_dynamic_value("{USERNAME:>5}|{USERNAME:.2}|{USERNAME:0>256}", variables) == (
        f"  bob|bo|{'0' * 253}bob"
    )
