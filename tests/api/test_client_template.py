from fastapi import status

from tests.api import client
from tests.api.helpers import auth_headers, create_client_template, create_core, delete_core, get_inbounds, unique_name


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
    # Clash always needs Jinja2 (it renders `conf`), enforced server-side regardless of what was requested.
    assert created["use_jinja"] is True

    response = client.get(
        f"/api/client_template/{created['id']}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == created["id"]


def test_client_template_can_use_user_variables(access_token):
    content = '{"remarks": "{{ USERNAME | upper }}", "inbounds": [{"tag": "in"}], "outbounds": [{"tag": "out"}]}'

    created = create_client_template(
        access_token, name=unique_name("tmpl_vars"), template_type="xray_subscription", content=content, use_jinja=True
    )
    assert created["content"] == content
    assert created["use_jinja"] is True

    # The same content saved as plain JSON (the default) is never rendered.
    plain = create_client_template(
        access_token, name=unique_name("tmpl_plain"), template_type="xray_subscription", content=content
    )
    assert plain["use_jinja"] is False


def test_client_template_validate_endpoint(access_token):
    body = '{\n"inbounds": [{}],\n"outbounds": [{}],\n"a": EXPR\n}'

    response = client.post(
        "/api/client_template/validate",
        headers=auth_headers(access_token),
        json={
            "template_type": "xray_subscription",
            "content": body.replace("EXPR", '"{{ USERNAME | upper }}"'),
            "use_jinja": True,
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"valid": True, "error": None, "line": None}

    invalid = {
        "template_type": "xray_subscription",
        "content": body.replace("EXPR", "{% if %}"),
        "use_jinja": True,
    }
    response = client.post("/api/client_template/validate", headers=auth_headers(access_token), json=invalid)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["valid"] is False
    assert response.json()["line"] == 4

    # Saving agrees with the check, and keeps its existing error format.
    response = client.post(
        "/api/client_template",
        headers=auth_headers(access_token),
        json={
            "name": unique_name("tmpl_invalid"),
            "template_type": "xray_subscription",
            "content": invalid["content"],
            "use_jinja": True,
        },
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"].startswith("Invalid template content: ")


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


def test_client_template_delete_clears_associated_host_override(access_token):
    core = create_core(access_token)
    inbound_list = get_inbounds(access_token)
    assert inbound_list, "No inbounds available for host template cleanup test"
    target = create_client_template(
        access_token,
        name=unique_name("tmpl_xray_host_cleanup"),
        template_type="xray_subscription",
        content='{"inbounds":[{"tag":"placeholder","protocol":"vmess","settings":{"clients":[]}}],"outbounds":[{"tag":"cleanup-template-marker","protocol":"freedom","settings":{}}]}',
    )

    host_id = None
    try:
        create_response = client.post(
            "/api/host",
            headers=auth_headers(access_token),
            json={
                "remark": unique_name("host_template_cleanup"),
                "address": ["127.0.0.1"],
                "port": 443,
                "inbound_tag": inbound_list[0],
                "priority": 1,
                "subscription_templates": {"xray": target["id"]},
            },
        )
        assert create_response.status_code == status.HTTP_201_CREATED
        host_id = create_response.json()["id"]
        assert create_response.json()["subscription_templates"] == {"xray": target["id"]}

        delete_response = client.delete(
            f"/api/client_template/{target['id']}",
            headers=auth_headers(access_token),
        )
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

        host_response = client.get(f"/api/host/{host_id}", headers=auth_headers(access_token))
        assert host_response.status_code == status.HTTP_200_OK
        assert host_response.json()["subscription_templates"] is None
    finally:
        if host_id is not None:
            client.delete(f"/api/host/{host_id}", headers=auth_headers(access_token))
        delete_core(access_token, core["id"])


def test_client_template_use_jinja_change_is_validated(access_token):
    broken = '{"inbounds": [{"tag": "{{ 1 + }}"}], "outbounds": [{"tag": "out"}]}'
    created = create_client_template(access_token, name=unique_name("tmpl_flip"), content=broken)
    assert created["use_jinja"] is False

    response = client.put(
        f"/api/client_template/{created['id']}",
        headers=auth_headers(access_token),
        json={"use_jinja": True},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    still = client.get(f"/api/client_template/{created['id']}", headers=auth_headers(access_token))
    assert still.json()["use_jinja"] is False
