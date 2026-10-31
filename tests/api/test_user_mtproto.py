import re
from uuid import uuid4

from fastapi import status

from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_group,
    create_mtproto_core,
    create_user,
    create_user_template,
    delete_core,
    delete_group,
    delete_user,
    delete_user_template,
    store_mtproto_secret,
    strip_mtproto_settings,
    unique_name,
)

_HEX32 = re.compile(r"[0-9a-f]{32}")
_SECRET = "00112233445566778899aabbccddeeff"


def _secret(user: dict) -> str | None:
    return user["proxy_settings"]["mtproto"]["secret"]


def _assert_hex32(secret) -> None:
    assert isinstance(secret, str) and _HEX32.fullmatch(secret), secret


def _get_user(access_token: str, user_id: int) -> dict:
    response = client.get(f"/api/user/by-id/{user_id}", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def _modify_user(access_token: str, user_id: int, payload: dict) -> dict:
    response = client.put(f"/api/user/by-id/{user_id}", headers=auth_headers(access_token), json=payload)
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


def _user_body(**proxy_settings) -> dict:
    return {
        "username": unique_name("mtp_user"),
        "proxy_settings": proxy_settings,
        "data_limit": 1024 * 1024,
        "data_limit_reset_strategy": "no_reset",
        "status": "active",
    }


def test_create_user_stores_generated_secret(access_token):
    user = create_user(access_token)
    try:
        _assert_hex32(_secret(user))
        assert _secret(_get_user(access_token, user["id"])) == _secret(user)
    finally:
        delete_user(access_token, user["username"])


def test_create_user_keeps_supplied_secret_lowercased(access_token):
    user = create_user(access_token, payload={"proxy_settings": {"mtproto": {"secret": _SECRET.upper()}}})
    try:
        assert _secret(user) == _SECRET
        assert _secret(_get_user(access_token, user["id"])) == _SECRET
    finally:
        delete_user(access_token, user["username"])


def test_create_user_rejects_duplicate_secret(access_token):
    secret = uuid4().hex
    first = create_user(access_token, payload={"proxy_settings": {"mtproto": {"secret": secret}}})
    second_body = _user_body(mtproto={"secret": secret})
    try:
        response = client.post("/api/user", headers=auth_headers(access_token), json=second_body)
        assert response.status_code == status.HTTP_400_BAD_REQUEST, response.text
        assert "already assigned" in response.json()["detail"]
    finally:
        delete_user(access_token, first["username"])
        if client.get(f"/api/user/{second_body['username']}", headers=auth_headers(access_token)).status_code == 200:
            delete_user(access_token, second_body["username"])


def test_secret_uniqueness_ignores_case_of_stored_secret(access_token):
    secret = uuid4().hex
    first = create_user(access_token)
    # Every write path lowercases; a hand-edited or legacy row can still hold uppercase hex.
    store_mtproto_secret(first["id"], secret.upper())
    second_body = _user_body(mtproto={"secret": secret})
    try:
        response = client.post("/api/user", headers=auth_headers(access_token), json=second_body)
        assert response.status_code == status.HTTP_400_BAD_REQUEST, response.text
        assert "already assigned" in response.json()["detail"]

        # The owner of that secret can still save it.
        modified = _modify_user(access_token, first["id"], {"proxy_settings": {"mtproto": {"secret": secret}}})
        assert _secret(modified) == secret
    finally:
        delete_user(access_token, first["username"])
        if client.get(f"/api/user/{second_body['username']}", headers=auth_headers(access_token)).status_code == 200:
            delete_user(access_token, second_body["username"])


def test_modify_keeps_secret_when_proxy_settings_omitted_or_partial(access_token):
    user = create_user(access_token)
    try:
        secret = _secret(user)
        _assert_hex32(secret)

        for payload in (
            {"note": "x"},
            {"proxy_settings": {"vless": {"id": str(uuid4())}}},
            {"proxy_settings": {"mtproto": {"secret": None}}},
        ):
            assert _secret(_modify_user(access_token, user["id"], payload)) == secret, payload
            assert _secret(_get_user(access_token, user["id"])) == secret, payload

        new_secret = uuid4().hex
        modified = _modify_user(access_token, user["id"], {"proxy_settings": {"mtproto": {"secret": new_secret}}})
        assert _secret(modified) == new_secret
        assert _secret(_get_user(access_token, user["id"])) == new_secret
    finally:
        delete_user(access_token, user["username"])


def test_read_path_never_invents_secret_and_first_save_assigns_one(access_token):
    user = create_user(access_token)
    try:
        strip_mtproto_settings(user["id"])
        assert _secret(_get_user(access_token, user["id"])) is None
        assert _secret(_get_user(access_token, user["id"])) is None

        secret = _secret(_modify_user(access_token, user["id"], {"note": "y"}))
        _assert_hex32(secret)
        assert _secret(_get_user(access_token, user["id"])) == secret
        assert _secret(_get_user(access_token, user["id"])) == secret
    finally:
        delete_user(access_token, user["username"])


def test_revoke_rotates_secret_and_keeps_policy_fields(access_token):
    secret = uuid4().hex
    user = create_user(
        access_token,
        payload={
            "proxy_settings": {
                "mtproto": {"secret": secret, "user_ad_tag": "ab" * 16, "max_tcp_conns": 5, "max_unique_ips": 2}
            }
        },
    )
    try:
        response = client.post(f"/api/user/by-id/{user['id']}/revoke_sub", headers=auth_headers(access_token))
        assert response.status_code == status.HTTP_200_OK, response.text
        mtproto = response.json()["proxy_settings"]["mtproto"]
        _assert_hex32(mtproto["secret"])
        assert mtproto["secret"] != secret
        assert mtproto["user_ad_tag"] == "ab" * 16
        assert mtproto["max_tcp_conns"] == 5
        assert mtproto["max_unique_ips"] == 2
        assert _get_user(access_token, user["id"])["proxy_settings"]["mtproto"] == mtproto
    finally:
        delete_user(access_token, user["username"])


def test_bulk_template_users_get_distinct_secrets(access_token):
    core = create_mtproto_core(access_token)
    group = create_group(access_token, inbound_tags=[core["config"]["inbound_tag"]])
    template = create_user_template(access_token, group_ids=[group["id"]])
    base_username = unique_name("mtp_bulk")
    count = 3
    usernames: list[str] = []
    try:
        response = client.post(
            "/api/users/bulk/from_template",
            headers=auth_headers(access_token),
            json={
                "user_template_id": template["id"],
                "strategy": "sequence",
                "username": base_username,
                "count": count,
                "start_number": 1,
            },
        )
        assert response.status_code == status.HTTP_201_CREATED, response.text
        assert response.json()["created"] == count
        usernames = [f"{base_username}{1 + idx}" for idx in range(count)]

        secrets = []
        for username in usernames:
            user_response = client.get(f"/api/user/{username}", headers=auth_headers(access_token))
            assert user_response.status_code == status.HTTP_200_OK
            secret = _secret(user_response.json())
            _assert_hex32(secret)
            secrets.append(secret)
        assert len(set(secrets)) == count
    finally:
        for username in usernames:
            delete_user(access_token, username)
        delete_user_template(access_token, template["id"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])


def test_invalid_policy_fields_rejected(access_token):
    for mtproto in ({"user_ad_tag": "nothex"}, {"max_tcp_conns": 4294967296}):
        body = _user_body(mtproto=mtproto)
        response = client.post("/api/user", headers=auth_headers(access_token), json=body)
        if response.status_code == status.HTTP_201_CREATED:
            delete_user(access_token, body["username"])
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, (mtproto, response.text)
