from fastapi import status

from tests.api import client
from tests.api.helpers import create_core_template, unique_name


def test_core_template_create_and_get(access_token):
    created = create_core_template(
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
        f"/api/core_template/{created['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == created["id"]


def test_core_template_can_switch_default(access_token):
    first = create_core_template(
        access_token,
        name=unique_name("tmpl_sb_first"),
        template_type="singbox_subscription",
        content='{"outbounds": []}',
    )
    second = create_core_template(
        access_token,
        name=unique_name("tmpl_sb_second"),
        template_type="singbox_subscription",
        content='{"outbounds": [{"tag": "a"}]}',
        is_default=True,
    )

    first_after = client.get(
        f"/api/core_template/{first['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()
    second_after = client.get(
        f"/api/core_template/{second['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()

    assert first_after["is_default"] is False
    assert second_after["is_default"] is True


def test_core_template_last_and_system_delete_guards(access_token):
    first = create_core_template(
        access_token,
        name=unique_name("tmpl_grpc_first"),
        template_type="grpc_user_agent",
        content='{"list": ["grpc-agent"]}',
    )

    response = client.delete(
        f"/api/core_template/{first['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    second = create_core_template(
        access_token,
        name=unique_name("tmpl_grpc_second"),
        template_type="grpc_user_agent",
        content='{"list": ["grpc-agent-2"]}',
    )

    response = client.delete(
        f"/api/core_template/{second['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    response = client.delete(
        f"/api/core_template/{first['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
