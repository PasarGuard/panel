"""
Nodes CLI Module

Handles node management through the command line interface.
"""

from app.db.base import get_db
from app.db.models import NodeStatus
from app.utils.helpers import readable_datetime
from cli import BaseCLI, console, get_node_operation


class NodeCLI(BaseCLI):
    """Node CLI operations."""

    async def list_nodes(self, db):
        """List all nodes."""
        node_op = get_node_operation()
        nodes = await node_op.get_db_nodes(db)

        if not nodes:
            self.console.print("[yellow]No nodes found[/yellow]")
            return

        table = self.create_table(
            "Nodes",
            [
                {"name": "ID", "style": "cyan"},
                {"name": "Name", "style": "green"},
                {"name": "Address", "style": "blue"},
                {"name": "Port", "style": "magenta"},
                {"name": "Status", "style": "yellow"},
                {"name": "Created At", "style": "white"},
            ],
        )

        for node in nodes:
            table.add_row(
                str(node.id),
                node.name,
                node.address,
                str(node.port),
                "Online" if node.status == NodeStatus.connected else "Offline",
                readable_datetime(node.created_at),
            )

        self.console.print(table)


# CLI commands
async def list_nodes():
    """List all nodes."""
    node_cli = NodeCLI()
    async for db in get_db():
        try:
            await node_cli.list_nodes(db)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            break
