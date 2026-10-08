from app.models.node import NodeCoreUpdate, NodeGeoFilesUpdate
from app.operation import OperatorType, node as node_operation_module
from app.operation.node import NodeOperation

# node-serviced runs update/core_update/geofiles with a 5 minute deadline.
NODE_SERVICED_DEADLINE_SECONDS = 300


async def test_maintenance_rpcs_wait_longer_than_node_serviced(monkeypatch):
    seen_timeouts = {}

    async def fake_request(action, payload, timeout=None):
        seen_timeouts[action] = timeout
        return {}

    monkeypatch.setattr(node_operation_module.node_nats_client, "request", fake_request)
    operation = NodeOperation(OperatorType.API)

    await operation._update_node_api_remote(1)
    await operation._update_core_remote(1, NodeCoreUpdate(core_version="v1.2.3"))
    await operation._update_geofiles_remote(1, NodeGeoFilesUpdate())

    assert set(seen_timeouts) == {"update_node_api", "update_core", "update_geofiles"}
    for action, timeout in seen_timeouts.items():
        assert timeout is not None and timeout > NODE_SERVICED_DEADLINE_SECONDS, (action, timeout)
