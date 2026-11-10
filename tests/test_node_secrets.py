from app.db.models import NodeConnectionType, NodeStatus
from app.models.admin import AdminDetails, AdminRoleData
from app.models.admin_role import NodesPermissions, RolePermissions
from app.models.node import NodeResponse
from app.operation.node import _can_view_node_secrets, _hide_node_secrets


def _admin(permissions: RolePermissions, *, is_owner: bool = False) -> AdminDetails:
    return AdminDetails(
        username="tester",
        role=AdminRoleData(is_owner=is_owner, permissions=permissions),
    )


def _node() -> NodeResponse:
    return NodeResponse(
        id=1,
        name="node",
        address="203.0.113.10",
        port=62050,
        api_port=62051,
        usage_coefficient=1.0,
        connection_type=NodeConnectionType.grpc,
        server_ca="-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----",
        keep_alive=60,
        core_config_id=1,
        api_key="node-api-key",
        xray_version=None,
        node_version=None,
        status=NodeStatus.connected,
        message=None,
    )


def test_read_only_role_cannot_view_node_api_key():
    read_only = _admin(RolePermissions(nodes=NodesPermissions(read=True, read_simple=True, stats=True)))
    assert _can_view_node_secrets(read_only) is False


def test_node_manager_and_owner_can_view_node_api_key():
    manager = _admin(RolePermissions(nodes=NodesPermissions(read=True, update=True)))
    owner = _admin(RolePermissions(), is_owner=True)
    assert _can_view_node_secrets(manager) is True
    assert _can_view_node_secrets(owner) is True
    assert _can_view_node_secrets(None) is False


def test_hide_node_secrets_clears_api_key():
    node = _hide_node_secrets(_node())
    assert node.api_key is None
    assert node.address == "203.0.113.10"
