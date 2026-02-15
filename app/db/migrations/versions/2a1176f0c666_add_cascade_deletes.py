"""add_cascade_deletes

Revision ID: 2a1176f0c666
Revises: 4f15c0789493
Create Date: 2026-02-15 15:00:06.236975

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "2a1176f0c666"
down_revision = "4f15c0789493"
branch_labels = None
depends_on = None


def get_fk_name(table_name, column_names):
    """Dynamically find the foreign key name for a given table and column(s)"""
    bind = op.get_bind()
    inspector = inspect(bind)
    fks = inspector.get_foreign_keys(table_name)
    for fk in fks:
        if set(fk["constrained_columns"]) == set(column_names):
            return fk["name"]
    return None


def get_index_name(table_name, column_names):
    """Dynamically find the index name for a given table and column(s)"""
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = inspector.get_indexes(table_name)
    for idx in indexes:
        if set(idx["column_names"]) == set(column_names):
            return idx["name"]
    return None


def upgrade() -> None:
    # --- hosts ---
    fk_hosts = get_fk_name("hosts", ["inbound_tag"])
    with op.batch_alter_table("hosts", schema=None) as batch_op:
        if fk_hosts:
            batch_op.drop_constraint(fk_hosts, type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_hosts_inbound_tag_inbounds",
            "inbounds",
            ["inbound_tag"],
            ["tag"],
            onupdate="CASCADE",
            ondelete="SET NULL",
        )

    # --- next_plans ---
    fk_np_temp = get_fk_name("next_plans", ["user_template_id"])
    fk_np_user = get_fk_name("next_plans", ["user_id"])
    idx_np_temp = get_index_name("next_plans", ["user_template_id"])
    with op.batch_alter_table("next_plans", schema=None) as batch_op:
        if idx_np_temp:
            batch_op.drop_index(idx_np_temp, if_exists=True)
        batch_op.create_index("ix_next_plans_user_template_id", ["user_template_id"], unique=False)
        if fk_np_temp:
            batch_op.drop_constraint(fk_np_temp, type_="foreignkey")
        if fk_np_user:
            batch_op.drop_constraint(fk_np_user, type_="foreignkey")
        batch_op.create_foreign_key("fk_next_plans_user_id_users", "users", ["user_id"], ["id"], ondelete="CASCADE")
        batch_op.create_foreign_key(
            "fk_next_plans_user_template_id_user_templates",
            "user_templates",
            ["user_template_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # --- node_usage_reset_logs ---
    fk_nurl = get_fk_name("node_usage_reset_logs", ["node_id"])
    idx_nurl = get_index_name("node_usage_reset_logs", ["node_id", "created_at"])
    with op.batch_alter_table("node_usage_reset_logs", schema=None) as batch_op:
        if idx_nurl:
            batch_op.drop_index(idx_nurl, if_exists=True)
        batch_op.create_index("ix_node_usage_reset_logs_node_id_created_at", ["node_id", "created_at"], unique=False)
        if fk_nurl:
            batch_op.drop_constraint(fk_nurl, type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_node_usage_reset_logs_node_id_nodes", "nodes", ["node_id"], ["id"], ondelete="CASCADE"
        )

    # --- node_usages ---
    fk_nu = get_fk_name("node_usages", ["node_id"])
    idx_nu = get_index_name("node_usages", ["created_at"])
    with op.batch_alter_table("node_usages", schema=None) as batch_op:
        if idx_nu:
            batch_op.drop_index(idx_nu, if_exists=True)
        batch_op.create_index("ix_node_usages_created_at", ["created_at"], unique=False)
        if fk_nu:
            batch_op.drop_constraint(fk_nu, type_="foreignkey")
        batch_op.create_foreign_key("fk_node_usages_node_id_nodes", "nodes", ["node_id"], ["id"], ondelete="CASCADE")

    # --- node_user_usages ---
    fk_nuu_node = get_fk_name("node_user_usages", ["node_id"])
    fk_nuu_user = get_fk_name("node_user_usages", ["user_id"])
    idx_nuu_1 = get_index_name("node_user_usages", ["created_at"])
    idx_nuu_2 = get_index_name("node_user_usages", ["node_id", "created_at"])
    idx_nuu_3 = get_index_name("node_user_usages", ["user_id", "created_at"])
    with op.batch_alter_table("node_user_usages", schema=None) as batch_op:
        if idx_nuu_1:
            batch_op.drop_index(idx_nuu_1, if_exists=True)
        if idx_nuu_2:
            batch_op.drop_index(idx_nuu_2, if_exists=True)
        if idx_nuu_3:
            batch_op.drop_index(idx_nuu_3, if_exists=True)
        batch_op.create_index("ix_node_user_usages_created_at", ["created_at"], unique=False)
        batch_op.create_index("ix_node_user_usages_node_id_created_at", ["node_id", "created_at"], unique=False)
        batch_op.create_index("ix_node_user_usages_user_id_created_at", ["user_id", "created_at"], unique=False)
        if fk_nuu_node:
            batch_op.drop_constraint(fk_nuu_node, type_="foreignkey")
        if fk_nuu_user:
            batch_op.drop_constraint(fk_nuu_user, type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_node_user_usages_node_id_nodes", "nodes", ["node_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_foreign_key(
            "fk_node_user_usages_user_id_users", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # --- notification_reminders ---
    fk_nr = get_fk_name("notification_reminders", ["user_id"])
    with op.batch_alter_table("notification_reminders", schema=None) as batch_op:
        if fk_nr:
            batch_op.drop_constraint(fk_nr, type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_notification_reminders_user_id_users", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # --- user_subscription_updates ---
    fk_usu = get_fk_name("user_subscription_updates", ["user_id"])
    with op.batch_alter_table("user_subscription_updates", schema=None) as batch_op:
        if fk_usu:
            batch_op.drop_constraint(fk_usu, type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_user_subscription_updates_user_id_users", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # --- user_usage_logs ---
    fk_uul = get_fk_name("user_usage_logs", ["user_id"])
    idx_uul = get_index_name("user_usage_logs", ["user_id", "reset_at"])
    with op.batch_alter_table("user_usage_logs", schema=None) as batch_op:
        if idx_uul:
            batch_op.drop_index(idx_uul, if_exists=True)
        batch_op.create_index("ix_user_usage_logs_user_id_reset_at", ["user_id", "reset_at"], unique=False)
        if fk_uul:
            batch_op.drop_constraint(fk_uul, type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_user_usage_logs_user_id_users", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )


def downgrade() -> None:
    # During downgrade, we drop the names WE created in upgrade and restore standard FKs
    with op.batch_alter_table("user_usage_logs", schema=None) as batch_op:
        batch_op.drop_constraint("fk_user_usage_logs_user_id_users", type_="foreignkey")
        batch_op.create_foreign_key(None, "users", ["user_id"], ["id"])
        batch_op.drop_index("ix_user_usage_logs_user_id_reset_at")

    with op.batch_alter_table("user_subscription_updates", schema=None) as batch_op:
        batch_op.drop_constraint("fk_user_subscription_updates_user_id_users", type_="foreignkey")
        batch_op.create_foreign_key(None, "users", ["user_id"], ["id"])

    with op.batch_alter_table("notification_reminders", schema=None) as batch_op:
        batch_op.drop_constraint("fk_notification_reminders_user_id_users", type_="foreignkey")
        batch_op.create_foreign_key(None, "users", ["user_id"], ["id"])

    with op.batch_alter_table("node_user_usages", schema=None) as batch_op:
        batch_op.drop_constraint("fk_node_user_usages_user_id_users", type_="foreignkey")
        batch_op.drop_constraint("fk_node_user_usages_node_id_nodes", type_="foreignkey")
        batch_op.create_foreign_key(None, "users", ["user_id"], ["id"])
        batch_op.create_foreign_key(None, "nodes", ["node_id"], ["id"])
        batch_op.drop_index("ix_node_user_usages_user_id_created_at")
        batch_op.drop_index("ix_node_user_usages_node_id_created_at")
        batch_op.drop_index("ix_node_user_usages_created_at")

    with op.batch_alter_table("node_usages", schema=None) as batch_op:
        batch_op.drop_constraint("fk_node_usages_node_id_nodes", type_="foreignkey")
        batch_op.create_foreign_key(None, "nodes", ["node_id"], ["id"])
        batch_op.drop_index("ix_node_usages_created_at")

    with op.batch_alter_table("node_usage_reset_logs", schema=None) as batch_op:
        batch_op.drop_constraint("fk_node_usage_reset_logs_node_id_nodes", type_="foreignkey")
        batch_op.create_foreign_key(None, "nodes", ["node_id"], ["id"])
        batch_op.drop_index("ix_node_usage_reset_logs_node_id_created_at")

    with op.batch_alter_table("next_plans", schema=None) as batch_op:
        batch_op.drop_constraint("fk_next_plans_user_template_id_user_templates", type_="foreignkey")
        batch_op.drop_constraint("fk_next_plans_user_id_users", type_="foreignkey")
        batch_op.create_foreign_key(None, "users", ["user_id"], ["id"])
        batch_op.create_foreign_key(None, "user_templates", ["user_template_id"], ["id"])
        batch_op.drop_index("ix_next_plans_user_template_id")

    with op.batch_alter_table("hosts", schema=None) as batch_op:
        batch_op.drop_constraint("fk_hosts_inbound_tag_inbounds", type_="foreignkey")
        batch_op.create_foreign_key(None, "inbounds", ["inbound_tag"], ["tag"])
