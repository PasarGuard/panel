"""add performance indexes

Revision ID: a1b2c3d4e5f6
Revises: fbfc49f01004
Create Date: 2026-06-14 12:00:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "fbfc49f01004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _create_index("idx_users_status", "users", ["status"])
    _create_index("idx_users_status_expire", "users", ["status", "expire"])
    _create_index("idx_users_status_used_traffic", "users", ["status", "used_traffic"])
    _create_index("idx_nodes_status", "nodes", ["status"])
    _create_index("idx_notification_reminders_user_id", "notification_reminders", ["user_id"])
    _create_index("idx_hosts_inbound_tag", "hosts", ["inbound_tag"])
    _create_index("idx_hosts_is_disabled", "hosts", ["is_disabled"])
    _create_index("idx_temp_keys_action", "temp_keys", ["action"])
    _create_index("idx_node_stats_node_id_created_at", "node_stats", ["node_id", "created_at"])


def downgrade() -> None:
    _drop_index("idx_node_stats_node_id_created_at", "node_stats")
    _drop_index("idx_temp_keys_action", "temp_keys")
    _drop_index("idx_hosts_is_disabled", "hosts")
    _drop_index("idx_hosts_inbound_tag", "hosts")
    _drop_index("idx_notification_reminders_user_id", "notification_reminders")
    _drop_index("idx_nodes_status", "nodes")
    _drop_index("idx_users_status_used_traffic", "users")
    _drop_index("idx_users_status_expire", "users")
    _drop_index("idx_users_status", "users")


def _create_index(name: str, table_name: str, columns: list) -> None:
    op.create_index(name, table_name, columns, unique=False, if_not_exists=True)


def _drop_index(name: str, table_name: str) -> None:
    op.drop_index(name, table_name=table_name)
