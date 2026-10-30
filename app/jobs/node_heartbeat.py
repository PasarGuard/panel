from app import on_shutdown, on_startup
from app.node.heartbeat import node_heartbeat
from config import runtime_settings


@on_startup
async def start_node_heartbeat():
    # Node objects live only in node-role processes.
    if not runtime_settings.role.runs_node:
        return
    node_heartbeat.start()
    on_shutdown(node_heartbeat.stop)
