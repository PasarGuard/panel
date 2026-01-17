from __future__ import annotations

from typing import Any, Iterable
from uuid import uuid4

from fastapi import status

from tests.api.sample_data import XRAY_CONFIG


def unique_name(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def strong_password(prefix: str) -> str:
    """Generate a password that always satisfies password policy."""
    suffix = unique_name("pwd").split("_")[-1]
    return f"{prefix}#12{suffix}"


def create_admin(
    access_token: str, *, username: str | None = None, password: str | None = None, is_sudo: bool = False
) -> dict:
    from tests.api import client
    username = username or unique_name("admin")
    # Ensure password always meets complexity rules (>=2 digits, 2 uppercase, 2 lowercase, special char)
    password = password or strong_password("TestAdmincreate")
    response = client.post(
        "/api/admin",
        headers=auth_headers(access_token),
        json={"username": username, "password": password, "is_sudo": is_sudo},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    data["password"] = password
    return data


def delete_admin(access_token: str, username: str) -> None:
    from tests.api import client
    response = client.delete(f"/api/admin/{username}", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_204_NO_CONTENT


def create_core(
    access_token: str,
    *,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    exclude: Iterable[str] | None = None,
    fallbacks: Iterable[str] | None = None,
) -> dict:
    from tests.api import client
    payload = {
        "config": config or XRAY_CONFIG,
        "name": name or unique_name("core"),
        "exclude_inbound_tags": list(exclude or []),
        "fallbacks_inbound_tags": list(fallbacks or ["fallback-A", "fallback-B"]),
    }
    response = client.post("/api/core", headers=auth_headers(access_token), json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def delete_core(access_token: str, core_id: int) -> None:
    from tests.api import client
    response = client.delete(f"/api/core/{core_id}", headers=auth_headers(access_token))

    assert response.status_code in (status.HTTP_204_NO_CONTENT, status.HTTP_403_FORBIDDEN)


def get_inbounds(access_token: str) -> list[str]:
    from tests.api import client
    response = client.get("/api/inbounds", headers=auth_headers(access_token))
    if response.status_code == status.HTTP_200_OK:
        return response.json()

    if response.status_code == status.HTTP_404_NOT_FOUND:
        core = create_core(access_token)
        try:
            response = client.get("/api/inbounds", headers=auth_headers(access_token))
            assert response.status_code == status.HTTP_200_OK
            return response.json()
        finally:
            delete_core(access_token, core["id"])

    raise AssertionError(f"Unexpected response from /api/inbounds: {response.status_code} {response.text}")


def create_hosts_for_inbounds(access_token: str, *, address: list[str] | None = None, port: int = 443) -> list[dict]:
    from tests.api import client
    inbounds = get_inbounds(access_token)
    hosts: list[dict] = []
    for idx, inbound in enumerate(inbounds):
        payload = {
            "remark": unique_name(f"host_{idx}"),
            "address": address or ["127.0.0.1"],
            "port": port,
            "sni": [f"test_host_{idx}.example.com"],
            "inbound_tag": inbound,
            "priority": idx + 1,
        }
        response = client.post("/api/host", headers=auth_headers(access_token), json=payload)
        assert response.status_code == status.HTTP_201_CREATED
        hosts.append(response.json())
    return hosts


def create_group(access_token: str, *, name: str | None = None, inbound_tags: Iterable[str] | None = None) -> dict:
    from tests.api import client
    tags = list(inbound_tags or [])
    if not tags:
        tags = get_inbounds(access_token)
    payload = {
        "name": name or unique_name("group"),
        "inbound_tags": tags,
    }
    response = client.post("/api/group", headers=auth_headers(access_token), json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def delete_group(access_token: str, group_id: int) -> None:
    from tests.api import client
    response = client.delete(f"/api/group/{group_id}", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_204_NO_CONTENT


def create_user(
    access_token: str,
    *,
    username: str | None = None,
    group_ids: Iterable[int] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict:
    from tests.api import client
    body = {
        "username": username or unique_name("user"),
        "proxy_settings": {},
        "data_limit": 1024 * 1024,
        "data_limit_reset_strategy": "no_reset",
        "status": "active",
    }
    if payload:
        body.update(payload)
    if group_ids is not None:
        body["group_ids"] = list(group_ids)
    response = client.post("/api/user", headers=auth_headers(access_token), json=body)
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def delete_user(access_token: str, username: str) -> None:
    from tests.api import client
    response = client.delete(f"/api/user/{username}", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_204_NO_CONTENT


def create_user_template(
    access_token: str,
    *,
    name: str | None = None,
    group_ids: Iterable[int],
    data_limit: int = 1024 * 1024 * 1024,
    expire_duration: int = 3600,
    extra_settings: dict[str, Any] | None = None,
    status_value: str = "active",
    reset_usages: bool = True,
) -> dict:
    from tests.api import client
    payload = {
        "name": name or unique_name("user_template"),
        "group_ids": list(group_ids),
        "data_limit": data_limit,
        "expire_duration": expire_duration,
        "extra_settings": extra_settings or {"flow": "", "method": None},
        "status": status_value,
        "reset_usages": reset_usages,
    }
    response = client.post("/api/user_template", headers=auth_headers(access_token), json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


def delete_user_template(access_token: str, template_id: int) -> None:
    from tests.api import client
    response = client.delete(f"/api/user_template/{template_id}", headers=auth_headers(access_token))
    assert response.status_code == status.HTTP_204_NO_CONTENT
