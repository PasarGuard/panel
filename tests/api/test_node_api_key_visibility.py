"""The node api_key is returned only to admins that may create or change nodes."""

import asyncio
from uuid import uuid4

import pytest
from fastapi import status
from sqlalchemy import select

from app.db.models import Node
from tests.api import TestSession, client
from tests.api.helpers import auth_headers, create_admin, delete_admin, unique_name

SERVER_CA = "-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----"


def _create_node_row(api_key: str) -> int:
    async def _create() -> int:
        async with TestSession() as session:
            node = Node(
                name=unique_name("node_api_key"),
                address="203.0.113.10",
                port=62050,
                api_port=62051,
                server_ca=SERVER_CA,
                api_key=api_key,
                core_config_id=None,
            )
            session.add(node)
            await session.commit()
            return node.id

    return asyncio.run(_create())


def _delete_node_row(node_id: int) -> None:
    async def _delete() -> None:
        async with TestSession() as session:
            row = (await session.execute(select(Node).where(Node.id == node_id))).scalar_one_or_none()
            if row is not None:
                await session.delete(row)
                await session.commit()

    asyncio.run(_delete())


@pytest.fixture
def node_with_key():
    api_key = str(uuid4())
    node_id = _create_node_row(api_key)
    yield node_id, api_key
    _delete_node_row(node_id)


@pytest.fixture
def node_reader(access_token):
    """Build a non-owner admin with the given nodes permissions and return its token."""
    created = []

    def _build(nodes_permissions: dict) -> str:
        response = client.post(
            "/api/admin-role",
            headers=auth_headers(access_token),
            json={
                "name": unique_name("role_node_api_key"),
                "permissions": {"nodes": nodes_permissions},
                "limits": {},
                "features": {},
                "access": {},
            },
        )
        assert response.status_code == status.HTTP_201_CREATED, response.text
        role = response.json()
        admin = create_admin(access_token, role_id=role["id"])
        created.append((role, admin))
        response = client.post(
            "/api/admin/token",
            data={"username": admin["username"], "password": admin["password"], "grant_type": "password"},
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        return response.json()["access_token"]

    yield _build

    for role, admin in created:
        delete_admin(access_token, admin["username"])
        client.delete(f"/api/admin-role/{role['id']}", headers=auth_headers(access_token))


def _listed_api_key(token: str, node_id: int):
    response = client.get("/api/nodes", headers=auth_headers(token))
    assert response.status_code == status.HTTP_200_OK, response.text
    nodes = {node["id"]: node for node in response.json()["nodes"]}
    return nodes[node_id]["api_key"]


def _single_api_key(token: str, node_id: int):
    response = client.get(f"/api/node/{node_id}", headers=auth_headers(token))
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()["api_key"]


def test_read_only_node_role_gets_no_api_key(node_with_key, node_reader):
    node_id, _ = node_with_key
    token = node_reader({"read": True})

    assert _listed_api_key(token, node_id) is None
    assert _single_api_key(token, node_id) is None


def test_node_update_role_gets_the_api_key(node_with_key, node_reader):
    node_id, api_key = node_with_key
    token = node_reader({"read": True, "update": True})

    assert _listed_api_key(token, node_id) == api_key
    assert _single_api_key(token, node_id) == api_key


def test_owner_gets_the_api_key(node_with_key, access_token):
    node_id, api_key = node_with_key

    assert _listed_api_key(access_token, node_id) == api_key
    assert _single_api_key(access_token, node_id) == api_key
