from fastapi import status

from tests.api import client
from tests.api.helpers import create_client_template, unique_name


def test_client_template_create_and_get(access_token):
    created = create_client_template(
        access_token,
        name=unique_name("tmpl_clash"),
        template_type="clash_subscription",
        content="proxies: []\nproxy-groups: []\nrules: []\n",
    )

    assert created["name"]
    assert created["template_type"] == "clash_subscription"
    assert created["content"]
    assert isinstance(created["is_default"], bool)
    assert isinstance(created["is_system"], bool)

    response = client.get(
        f"/api/client_template/{created['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == created["id"]


def test_client_template_can_switch_default(access_token):
    first = create_client_template(
        access_token,
        name=unique_name("tmpl_sb_first"),
        template_type="singbox_subscription",
        content='{"outbounds": [{"type": "direct", "tag": "a"}],"inbounds":[{"type": "socks5","tag":"b","settings":{"clients":[{"username":"user","password":"pass"}]}}]}',
    )
    second = create_client_template(
        access_token,
        name=unique_name("tmpl_sb_second"),
        template_type="singbox_subscription",
        content='{"outbounds": [{"type": "direct", "tag": "a"}],"inbounds":[{"type": "socks5","tag":"b","settings":{"clients":[{"username":"user","password":"pass"}]}}]}',
        is_default=True,
    )

    first_after = client.get(
        f"/api/client_template/{first['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()
    second_after = client.get(
        f"/api/client_template/{second['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()

    assert first_after["is_default"] is False
    assert second_after["is_default"] is True


def test_client_template_cannot_delete_first_template(access_token):
    response = client.get(
        "/api/client_templates",
        params={"template_type": "grpc_user_agent"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    templates = response.json()["templates"]

    if templates:
        first = min(templates, key=lambda template: template["id"])
    else:
        first = create_client_template(
            access_token,
            name=unique_name("tmpl_grpc_first"),
            template_type="grpc_user_agent",
            content='{"list": ["grpc-agent"]}',
        )

    response = client.delete(
        f"/api/client_template/{first['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_client_template_can_delete_non_first_template(access_token):
    response = client.get(
        "/api/client_templates",
        params={"template_type": "grpc_user_agent"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    templates = response.json()["templates"]

    if not templates:
        create_client_template(
            access_token,
            name=unique_name("tmpl_grpc_seed_first"),
            template_type="grpc_user_agent",
            content='{"list": ["grpc-agent-seed"]}',
        )

    second = create_client_template(
        access_token,
        name=unique_name("tmpl_grpc_second"),
        template_type="grpc_user_agent",
        content='{"list": ["grpc-agent-2"]}',
    )

    response = client.delete(
        f"/api/client_template/{second['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
