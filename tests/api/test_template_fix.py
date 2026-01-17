
import pytest
from tests.api import client
from fastapi import status

def test_user_template_node_limits_persistence(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # 1. Create a dummy node (if not exists)
    # We can use the existing /api/node endpoint synchronously
    node_data = {
        "name": "Test Node Tpl Fix Sync",
        "address": "127.0.0.1",
        "port": 9091, 
        "connection_type": "grpc",
        "server_ca": "test-ca",
        "keep_alive": 40,
        "api_key": "test-key-tpl-sync",
        "core_config_id": 1 
    }
    
    # Check if we can list nodes
    nodes_res = client.get("/api/node", headers=headers)
    node_id = None
    if nodes_res.status_code == 200 and nodes_res.json()["total"] > 0:
        node_id = nodes_res.json()["nodes"][0]["id"]
    else:
        # Create core first
        core_payload = {"name": "Test Core Tpl Sync", "config": {}}
        c_res = client.post("/api/core", json=core_payload, headers=headers)
        print(f"DEBUG CORE CREATE: {c_res.status_code} {c_res.text}")
        
        node_res = client.post("/api/node", json=node_data, headers=headers)
        print(f"DEBUG NODE CREATE: {node_res.status_code} {node_res.text}")
        if node_res.status_code == 200:
            node_id = node_res.json()["id"]
    
    if not node_id:
        print("DEBUG: SKIPPING DUE TO NO NODE ID")
        pytest.skip("Could not create or find a node for testing")

    # 2. Create User Template with limits
    limit_bytes = 1024 * 1024 * 1024 # 1GB
    template_payload = {
        "name": "Test Limit Persistence Sync",
        "group_ids": [],
        "node_user_limits": {
            str(node_id): {
                "data_limit": limit_bytes,
                "data_limit_reset_strategy": "month"
            }
        }
    }
    
    res = client.post("/api/user_template", json=template_payload, headers=headers)
    assert res.status_code == 201, f"Create failed: {res.text}"
    tpl = res.json()
    print(f"DEBUG RESPONSE: {tpl}")
    
    # 3. Verify Response has limits
    assert tpl.get("node_user_limits") is not None, "node_user_limits is None in response"
    assert str(node_id) in tpl["node_user_limits"], "node_id not in node_user_limits"
    
    saved_limit = tpl["node_user_limits"][str(node_id)]
    if isinstance(saved_limit, dict):
        assert saved_limit["data_limit"] == limit_bytes
    else:
        assert saved_limit == limit_bytes

    # 4. Verify Fetch has limits
    res_get = client.get(f"/api/user_template/{tpl['id']}", headers=headers)
    assert res_get.status_code == 200
    tpl_get = res_get.json()
    
    assert tpl_get.get("node_user_limits") is not None, "node_user_limits is None in GET response"
    assert str(node_id) in tpl_get["node_user_limits"]

    # 5. Modify Template (Change limit)
    new_limit_bytes = 2 * 1024 * 1024 * 1024
    modify_payload = {
        "node_user_limits": {
            str(node_id): {
                "data_limit": new_limit_bytes,
                "data_limit_reset_strategy": "week"
            }
        }
    }
    res_mod = client.put(f"/api/user_template/{tpl['id']}", json=modify_payload, headers=headers)
    assert res_mod.status_code == 200
    tpl_mod = res_mod.json()
    
    assert tpl_mod["node_user_limits"][str(node_id)]["data_limit"] == new_limit_bytes
    
    # Cleanup
    client.delete(f"/api/user_template/{tpl['id']}", headers=headers)
