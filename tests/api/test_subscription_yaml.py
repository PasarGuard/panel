import random

import pytest
import yaml

from app.subscription import config_cache
from app.templates import filters
from tests.api import client
from tests.api.helpers import (
    auth_headers,
    create_core,
    create_group,
    create_user,
    delete_core,
    delete_group,
    delete_user,
    get_inbound_details,
)


@pytest.mark.skipif(not yaml.__with_libyaml__, reason="libyaml is not available")
def test_clash_subscriptions_match_pure_yaml_dumper(access_token, monkeypatch):
    headers = auth_headers(access_token)
    core = create_core(access_token)
    details = get_inbound_details(access_token)
    group = create_group(access_token, inbound_tags=[detail["tag"] for detail in details])
    user = create_user(access_token, group_ids=[group["id"]])
    host_ids = []
    fast_dumper = filters._FastDumper

    try:
        for index, detail in enumerate(details):
            payload = {
                "remark": f"🇩🇪 {{USERNAME}} {detail['tag']} ✅ {{DATA_LEFT}} 🚀",
                "address": [f"198.51.100.{index + 1}"],
                "port": 443,
                "inbound_tag": detail["tag"],
                "priority": index,
            }
            if detail["protocol"] != "wireguard":
                payload["sni"] = [f"s{index}.example.com"]
            response = client.post("/api/host", headers=headers, json=payload)
            assert response.status_code == 201, response.text
            host_ids.append(response.json()["id"])

        for client_type in ("clash", "clash_meta"):
            bodies = []
            for dumper in (fast_dumper, None):
                monkeypatch.setattr(filters, "_FastDumper", dumper)
                config_cache.clear_sub_config_cache()
                # Reality short ids are picked at random per render
                random.seed(1052)
                response = client.get(f"{user['subscription_url']}/{client_type}")
                assert response.status_code == 200
                bodies.append(response.content)

            assert "🇩🇪".encode() in bodies[0]
            assert bodies[0] == bodies[1]
    finally:
        monkeypatch.setattr(filters, "_FastDumper", fast_dumper)
        for host_id in host_ids:
            client.delete(f"/api/host/{host_id}", headers=headers)
        delete_user(access_token, user["username"])
        delete_group(access_token, group["id"])
        delete_core(access_token, core["id"])
