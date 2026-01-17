
import pytest
from app.models.node import Node, NodeCreate, NodeModify, DataLimitResetStrategy
from app.models.user_template import UserTemplateCreate, UserTemplate
from httpx import AsyncClient

# Test script to verify data limit fixes (User 0GB issue and Node Modify issue)

@pytest.mark.asyncio
async def test_node_limits_defaults(client: AsyncClient, get_panel_api_headers):
    """
    Test 1: Create a Node. Verify user_data_limit is None (Unlimited) by default.
    """
    # Create a dummy node payload
    node_data = {
        "name": "Test Node Limit",
        "address": "127.0.0.1",
        "port": 8081,
        "api_port": 8082,
        "connection_type": "grpc",
        "server_ca": "test-ca",
        "keep_alive": 40,
        "api_key": "test-key",
        "core_config_id": 1 # Assuming core config 1 exists, if not we might need to create it or mock
    }
    
    # Needs a core config. Let's assume standard test setup provides it or we catch error.
    # In integration tests, we usually have `setup_core_config` fixture or similar.
    # We will try to rely on existing fixtures or just see if it works.
    # If standard fixtures are needed, we might need to import them or use what's available.
    
    # We will assume a core config 1 might not exist.
    # Lets try to create one first if we stick to strict integration
    
    # Create Core Config
    core_payload = {
        "name": "Test Core Limits",
        "config": {}
    }
    core_res = await client.post("/api/core", json=core_payload, headers=get_panel_api_headers)
    if core_res.status_code == 200:
        core_id = core_res.json()["id"]
        node_data["core_config_id"] = core_id
    else:
        # Fallback or fail. If fail, maybe core 1 exists.
        pass

    response = await client.post("/api/node", json=node_data, headers=get_panel_api_headers)
    assert response.status_code == 200, f"Node creation failed: {response.text}"
    
    node = response.json()
    node_id = node["id"]
    
    # VERIFY: user_data_limit should be None
    assert node["user_data_limit"] is None, f"Expected user_data_limit to be None, got {node['user_data_limit']}"
    assert node["data_limit"] is None, f"Expected data_limit to be None, got {node['data_limit']}"

    # Test 2: Modify Node. Set user_data_limit to 10GB (10 * 1024^3). Verify.
    limit_10gb = 10 * 1024 * 1024 * 1024
    modify_payload = {
        "user_data_limit": limit_10gb
    }
    res_mod = await client.put(f"/api/node/{node_id}", json=modify_payload, headers=get_panel_api_headers)
    assert res_mod.status_code == 200
    node_mod = res_mod.json()
    assert node_mod["user_data_limit"] == limit_10gb, "Failed to set user_data_limit"

    # Test 3: Modify Node. Set user_data_limit to None. Verify it goes back to None.
    # The frontend sends null.
    modify_payload_none = {
        "user_data_limit": None
    }
    res_mod_none = await client.put(f"/api/node/{node_id}", json=modify_payload_none, headers=get_panel_api_headers)
    assert res_mod_none.status_code == 200, f"Failed to unset limit: {res_mod_none.text}"
    node_mod_none = res_mod_none.json()
    assert node_mod_none["user_data_limit"] is None, "Failed to revert user_data_limit to None"

    # Cleanup
    await client.delete(f"/api/node/{node_id}", headers=get_panel_api_headers)

@pytest.mark.asyncio
async def test_user_template_node_limits(client: AsyncClient, get_panel_api_headers):
    """
    Test 4: Create User Template with node_user_limits. Verify success.
    """
    # Create User Template with node limits
    # Assuming node 1 exists or we can use a random ID (the validation might check existence?)
    # Usually template validation doesn't check if node exists strictly unless FK enforced?
    # But let's create a node to be safe.
    
    # Recreate node logic from above roughly
    core_payload = {"name": "Test Core Tpl", "config": {}}
    core_res = await client.post("/api/core", json=core_payload, headers=get_panel_api_headers)
    try:
        core_id = core_res.json().get("id", 1)
    except:
        core_id = 1

    node_data = {
        "name": "Test Node Tpl",
        "address": "127.0.0.1",
        "port": 8083,
        "connection_type": "grpc",
        "server_ca": "test-ca",
        "keep_alive": 40,
        "api_key": "test-key",
        "core_config_id": core_id
    }
    node_res = await client.post("/api/node", json=node_data, headers=get_panel_api_headers)
    if node_res.status_code == 200:
        node_id = node_res.json()["id"]
    else:
        # Fallback
        node_id = 1
        
    template_payload = {
        "name": "Test Limit Template",
        "data_limit": 5 * 1024 * 1024 * 1024, # 5GB
        "expire_duration": 30 * 24 * 3600,
        "group_ids": [],
        "node_user_limits": {
            str(node_id): {
                "data_limit": 1024 * 1024 * 1024, # 1GB
                "data_limit_reset_strategy": "month"
            }
        }
    }
    
    res_tpl = await client.post("/api/user_template", json=template_payload, headers=get_panel_api_headers)
    assert res_tpl.status_code == 200, f"Template creation failed: {res_tpl.text}"
    
    tpl = res_tpl.json()
    assert str(node_id) in tpl["node_user_limits"] or node_id in tpl["node_user_limits"]
    
    # Cleanup
    await client.delete(f"/api/user_template/{tpl['id']}", headers=get_panel_api_headers)
    if node_res.status_code == 200:
        await client.delete(f"/api/node/{node_id}", headers=get_panel_api_headers)

