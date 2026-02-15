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


def index_exists(table_name, index_name):
    """Check if an index exists"""
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx["name"] == index_name for idx in indexes)


def _delete_orphan_rows(child_table, child_column, parent_table, parent_column="id"):
    """Delete child rows that reference missing parent rows."""
    child = sa.table(child_table, sa.column(child_column))
    parent = sa.table(parent_table, sa.column(parent_column))
    op.execute(
        sa.delete(child).where(
            child.c[child_column].is_not(None),
            ~sa.exists(
                sa.select(1)
                .select_from(parent)
                .where(parent.c[parent_column] == child.c[child_column])
            ),
        )
    )


def _null_orphan_refs(child_table, child_column, parent_table, parent_column="id"):
    """Set orphaned FK-like references to NULL for SET NULL relationships."""
    child = sa.table(child_table, sa.column(child_column))
    parent = sa.table(parent_table, sa.column(parent_column))
    op.execute(
        sa.update(child)
        .where(
            child.c[child_column].is_not(None),
            ~sa.exists(
                sa.select(1)
                .select_from(parent)
                .where(parent.c[parent_column] == child.c[child_column])
            ),
        )
        .values({child_column: None})
    )


def _cleanup_orphan_references() -> None:
    """Normalize legacy rows so FK creation does not fail on dirty datasets."""
    _null_orphan_refs("hosts", "inbound_tag", "inbounds", parent_column="tag")

    _delete_orphan_rows("next_plans", "user_id", "users")
    _null_orphan_refs("next_plans", "user_template_id", "user_templates")

    _delete_orphan_rows("node_usage_reset_logs", "node_id", "nodes")
    _delete_orphan_rows("node_usages", "node_id", "nodes")
    _delete_orphan_rows("node_user_usages", "node_id", "nodes")
    _delete_orphan_rows("node_user_usages", "user_id", "users")

    _delete_orphan_rows("notification_reminders", "user_id", "users")
    _delete_orphan_rows("user_subscription_updates", "user_id", "users")
    _delete_orphan_rows("user_usage_logs", "user_id", "users")


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    _cleanup_orphan_references()
    
    # SQLite needs batch operations, MySQL/PostgreSQL use direct operations
    if dialect_name == 'sqlite':
        _upgrade_sqlite()
    else:
        _upgrade_mysql_postgres()


def _upgrade_sqlite() -> None:
    """SQLite-specific upgrade using batch_alter_table"""
    
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
    with op.batch_alter_table("next_plans", schema=None) as batch_op:
        if not index_exists("next_plans", "ix_next_plans_user_template_id"):
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
    with op.batch_alter_table("node_usage_reset_logs", schema=None) as batch_op:
        if not index_exists("node_usage_reset_logs", "ix_node_usage_reset_logs_node_id_created_at"):
            batch_op.create_index("ix_node_usage_reset_logs_node_id_created_at", ["node_id", "created_at"], unique=False)
        if fk_nurl:
            batch_op.drop_constraint(fk_nurl, type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_node_usage_reset_logs_node_id_nodes", "nodes", ["node_id"], ["id"], ondelete="CASCADE"
        )

    # --- node_usages ---
    fk_nu = get_fk_name("node_usages", ["node_id"])
    with op.batch_alter_table("node_usages", schema=None) as batch_op:
        if not index_exists("node_usages", "ix_node_usages_created_at"):
            batch_op.create_index("ix_node_usages_created_at", ["created_at"], unique=False)
        if fk_nu:
            batch_op.drop_constraint(fk_nu, type_="foreignkey")
        batch_op.create_foreign_key("fk_node_usages_node_id_nodes", "nodes", ["node_id"], ["id"], ondelete="CASCADE")

    # --- node_user_usages ---
    fk_nuu_node = get_fk_name("node_user_usages", ["node_id"])
    fk_nuu_user = get_fk_name("node_user_usages", ["user_id"])
    with op.batch_alter_table("node_user_usages", schema=None) as batch_op:
        if not index_exists("node_user_usages", "ix_node_user_usages_created_at"):
            batch_op.create_index("ix_node_user_usages_created_at", ["created_at"], unique=False)
        if not index_exists("node_user_usages", "ix_node_user_usages_node_id_created_at"):
            batch_op.create_index("ix_node_user_usages_node_id_created_at", ["node_id", "created_at"], unique=False)
        if not index_exists("node_user_usages", "ix_node_user_usages_user_id_created_at"):
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
    with op.batch_alter_table("user_usage_logs", schema=None) as batch_op:
        if not index_exists("user_usage_logs", "ix_user_usage_logs_user_id_reset_at"):
            batch_op.create_index("ix_user_usage_logs_user_id_reset_at", ["user_id", "reset_at"], unique=False)
        if fk_uul:
            batch_op.drop_constraint(fk_uul, type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_user_usage_logs_user_id_users", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )


def _upgrade_mysql_postgres() -> None:
    """MySQL/PostgreSQL upgrade using direct operations"""
    
    # --- hosts ---
    fk_hosts = get_fk_name("hosts", ["inbound_tag"])
    if fk_hosts:
        op.drop_constraint(fk_hosts, "hosts", type_="foreignkey")
    op.create_foreign_key(
        "fk_hosts_inbound_tag_inbounds",
        "hosts",
        "inbounds",
        ["inbound_tag"],
        ["tag"],
        onupdate="CASCADE",
        ondelete="SET NULL",
    )

    # --- next_plans ---
    if not index_exists("next_plans", "ix_next_plans_user_template_id"):
        op.create_index("ix_next_plans_user_template_id", "next_plans", ["user_template_id"], unique=False)
    
    fk_np_temp = get_fk_name("next_plans", ["user_template_id"])
    fk_np_user = get_fk_name("next_plans", ["user_id"])
    if fk_np_temp:
        op.drop_constraint(fk_np_temp, "next_plans", type_="foreignkey")
    if fk_np_user:
        op.drop_constraint(fk_np_user, "next_plans", type_="foreignkey")
    op.create_foreign_key("fk_next_plans_user_id_users", "next_plans", "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key(
        "fk_next_plans_user_template_id_user_templates",
        "next_plans",
        "user_templates",
        ["user_template_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- node_usage_reset_logs ---
    if not index_exists("node_usage_reset_logs", "ix_node_usage_reset_logs_node_id_created_at"):
        op.create_index("ix_node_usage_reset_logs_node_id_created_at", "node_usage_reset_logs", ["node_id", "created_at"], unique=False)
    
    fk_nurl = get_fk_name("node_usage_reset_logs", ["node_id"])
    if fk_nurl:
        op.drop_constraint(fk_nurl, "node_usage_reset_logs", type_="foreignkey")
    op.create_foreign_key(
        "fk_node_usage_reset_logs_node_id_nodes", "node_usage_reset_logs", "nodes", ["node_id"], ["id"], ondelete="CASCADE"
    )

    # --- node_usages ---
    if not index_exists("node_usages", "ix_node_usages_created_at"):
        op.create_index("ix_node_usages_created_at", "node_usages", ["created_at"], unique=False)
    
    fk_nu = get_fk_name("node_usages", ["node_id"])
    if fk_nu:
        op.drop_constraint(fk_nu, "node_usages", type_="foreignkey")
    op.create_foreign_key("fk_node_usages_node_id_nodes", "node_usages", "nodes", ["node_id"], ["id"], ondelete="CASCADE")

    # --- node_user_usages ---
    if not index_exists("node_user_usages", "ix_node_user_usages_created_at"):
        op.create_index("ix_node_user_usages_created_at", "node_user_usages", ["created_at"], unique=False)
    if not index_exists("node_user_usages", "ix_node_user_usages_node_id_created_at"):
        op.create_index("ix_node_user_usages_node_id_created_at", "node_user_usages", ["node_id", "created_at"], unique=False)
    if not index_exists("node_user_usages", "ix_node_user_usages_user_id_created_at"):
        op.create_index("ix_node_user_usages_user_id_created_at", "node_user_usages", ["user_id", "created_at"], unique=False)
    
    fk_nuu_node = get_fk_name("node_user_usages", ["node_id"])
    fk_nuu_user = get_fk_name("node_user_usages", ["user_id"])
    if fk_nuu_node:
        op.drop_constraint(fk_nuu_node, "node_user_usages", type_="foreignkey")
    if fk_nuu_user:
        op.drop_constraint(fk_nuu_user, "node_user_usages", type_="foreignkey")
    op.create_foreign_key(
        "fk_node_user_usages_node_id_nodes", "node_user_usages", "nodes", ["node_id"], ["id"], ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_node_user_usages_user_id_users", "node_user_usages", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )

    # --- notification_reminders ---
    fk_nr = get_fk_name("notification_reminders", ["user_id"])
    if fk_nr:
        op.drop_constraint(fk_nr, "notification_reminders", type_="foreignkey")
    op.create_foreign_key(
        "fk_notification_reminders_user_id_users", "notification_reminders", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )

    # --- user_subscription_updates ---
    fk_usu = get_fk_name("user_subscription_updates", ["user_id"])
    if fk_usu:
        op.drop_constraint(fk_usu, "user_subscription_updates", type_="foreignkey")
    op.create_foreign_key(
        "fk_user_subscription_updates_user_id_users", "user_subscription_updates", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )

    # --- user_usage_logs ---
    if not index_exists("user_usage_logs", "ix_user_usage_logs_user_id_reset_at"):
        op.create_index("ix_user_usage_logs_user_id_reset_at", "user_usage_logs", ["user_id", "reset_at"], unique=False)
    
    fk_uul = get_fk_name("user_usage_logs", ["user_id"])
    if fk_uul:
        op.drop_constraint(fk_uul, "user_usage_logs", type_="foreignkey")
    op.create_foreign_key(
        "fk_user_usage_logs_user_id_users", "user_usage_logs", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    
    if dialect_name == 'sqlite':
        _downgrade_sqlite()
    else:
        _downgrade_mysql_postgres()


def _downgrade_sqlite() -> None:
    """SQLite-specific downgrade"""
    
    with op.batch_alter_table("user_usage_logs", schema=None) as batch_op:
        batch_op.drop_constraint("fk_user_usage_logs_user_id_users", type_="foreignkey")
        batch_op.create_foreign_key(None, "users", ["user_id"], ["id"])
        if index_exists("user_usage_logs", "ix_user_usage_logs_user_id_reset_at"):
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
        if index_exists("node_user_usages", "ix_node_user_usages_user_id_created_at"):
            batch_op.drop_index("ix_node_user_usages_user_id_created_at")
        if index_exists("node_user_usages", "ix_node_user_usages_node_id_created_at"):
            batch_op.drop_index("ix_node_user_usages_node_id_created_at")
        if index_exists("node_user_usages", "ix_node_user_usages_created_at"):
            batch_op.drop_index("ix_node_user_usages_created_at")

    with op.batch_alter_table("node_usages", schema=None) as batch_op:
        batch_op.drop_constraint("fk_node_usages_node_id_nodes", type_="foreignkey")
        batch_op.create_foreign_key(None, "nodes", ["node_id"], ["id"])
        if index_exists("node_usages", "ix_node_usages_created_at"):
            batch_op.drop_index("ix_node_usages_created_at")

    with op.batch_alter_table("node_usage_reset_logs", schema=None) as batch_op:
        batch_op.drop_constraint("fk_node_usage_reset_logs_node_id_nodes", type_="foreignkey")
        batch_op.create_foreign_key(None, "nodes", ["node_id"], ["id"])
        if index_exists("node_usage_reset_logs", "ix_node_usage_reset_logs_node_id_created_at"):
            batch_op.drop_index("ix_node_usage_reset_logs_node_id_created_at")

    with op.batch_alter_table("next_plans", schema=None) as batch_op:
        batch_op.drop_constraint("fk_next_plans_user_template_id_user_templates", type_="foreignkey")
        batch_op.drop_constraint("fk_next_plans_user_id_users", type_="foreignkey")
        batch_op.create_foreign_key(None, "users", ["user_id"], ["id"])
        batch_op.create_foreign_key(None, "user_templates", ["user_template_id"], ["id"])
        if index_exists("next_plans", "ix_next_plans_user_template_id"):
            batch_op.drop_index("ix_next_plans_user_template_id")

    with op.batch_alter_table("hosts", schema=None) as batch_op:
        batch_op.drop_constraint("fk_hosts_inbound_tag_inbounds", type_="foreignkey")
        batch_op.create_foreign_key(None, "inbounds", ["inbound_tag"], ["tag"])


def _downgrade_mysql_postgres() -> None:
    """MySQL/PostgreSQL downgrade"""
    
    op.drop_constraint("fk_user_usage_logs_user_id_users", "user_usage_logs", type_="foreignkey")
    op.create_foreign_key(None, "user_usage_logs", "users", ["user_id"], ["id"])
    if index_exists("user_usage_logs", "ix_user_usage_logs_user_id_reset_at"):
        op.drop_index("ix_user_usage_logs_user_id_reset_at", "user_usage_logs")

    op.drop_constraint("fk_user_subscription_updates_user_id_users", "user_subscription_updates", type_="foreignkey")
    op.create_foreign_key(None, "user_subscription_updates", "users", ["user_id"], ["id"])

    op.drop_constraint("fk_notification_reminders_user_id_users", "notification_reminders", type_="foreignkey")
    op.create_foreign_key(None, "notification_reminders", "users", ["user_id"], ["id"])

    op.drop_constraint("fk_node_user_usages_user_id_users", "node_user_usages", type_="foreignkey")
    op.drop_constraint("fk_node_user_usages_node_id_nodes", "node_user_usages", type_="foreignkey")
    op.create_foreign_key(None, "node_user_usages", "users", ["user_id"], ["id"])
    op.create_foreign_key(None, "node_user_usages", "nodes", ["node_id"], ["id"])
    if index_exists("node_user_usages", "ix_node_user_usages_user_id_created_at"):
        op.drop_index("ix_node_user_usages_user_id_created_at", "node_user_usages")
    if index_exists("node_user_usages", "ix_node_user_usages_node_id_created_at"):
        op.drop_index("ix_node_user_usages_node_id_created_at", "node_user_usages")
    if index_exists("node_user_usages", "ix_node_user_usages_created_at"):
        op.drop_index("ix_node_user_usages_created_at", "node_user_usages")

    op.drop_constraint("fk_node_usages_node_id_nodes", "node_usages", type_="foreignkey")
    op.create_foreign_key(None, "node_usages", "nodes", ["node_id"], ["id"])
    if index_exists("node_usages", "ix_node_usages_created_at"):
        op.drop_index("ix_node_usages_created_at", "node_usages")

    op.drop_constraint("fk_node_usage_reset_logs_node_id_nodes", "node_usage_reset_logs", type_="foreignkey")
    op.create_foreign_key(None, "node_usage_reset_logs", "nodes", ["node_id"], ["id"])
    if index_exists("node_usage_reset_logs", "ix_node_usage_reset_logs_node_id_created_at"):
        op.drop_index("ix_node_usage_reset_logs_node_id_created_at", "node_usage_reset_logs")

    op.drop_constraint("fk_next_plans_user_template_id_user_templates", "next_plans", type_="foreignkey")
    op.drop_constraint("fk_next_plans_user_id_users", "next_plans", type_="foreignkey")
    op.create_foreign_key(None, "next_plans", "users", ["user_id"], ["id"])
    op.create_foreign_key(None, "next_plans", "user_templates", ["user_template_id"], ["id"])
    if index_exists("next_plans", "ix_next_plans_user_template_id"):
        op.drop_index("ix_next_plans_user_template_id", "next_plans")

    op.drop_constraint("fk_hosts_inbound_tag_inbounds", "hosts", type_="foreignkey")
    op.create_foreign_key(None, "hosts", "inbounds", ["inbound_tag"], ["tag"])
