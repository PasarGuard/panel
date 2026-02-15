"""use bigint for id column

Revision ID: 4f15c0789493
Revises: 5213b80a795c
Create Date: 2026-02-15 10:41:49.611553

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '4f15c0789493'
down_revision = '5213b80a795c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == 'sqlite':
        # SQLite doesn't have the 2.1B sequence limit problem
        # INTEGER in SQLite is already 64-bit signed (can hold up to 2^63-1)
        # Skip this migration for SQLite test databases
        pass
    elif dialect_name == 'mysql':
        _upgrade_mysql()
    else:
        # PostgreSQL
        _upgrade_postgresql()


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == 'sqlite':
        pass  # No-op for SQLite
    elif dialect_name == 'mysql':
        _downgrade_mysql()
    else:
        _downgrade_postgresql()


def _get_foreign_keys_for_table(table_name):
    """Get all foreign key constraints for a table"""
    bind = op.get_bind()
    inspector = inspect(bind)
    return inspector.get_foreign_keys(table_name)


def _upgrade_mysql() -> None:
    """MySQL: Drop FKs, alter columns, recreate FKs"""

    tables_with_fks = [
        'admin_usage_logs', 'users', 'nodes', 'node_stats', 'node_usages',
        'node_user_usages', 'node_usage_reset_logs', 'notification_reminders',
        'user_usage_logs', 'user_subscription_updates', 'next_plans',
        'inbounds_groups_association', 'users_groups_association', 'template_group_association',
    ]

    # Step 1: Drop FKs and save metadata
    fk_info = {}
    for table_name in tables_with_fks:
        fks = _get_foreign_keys_for_table(table_name)
        fk_info[table_name] = fks
        for fk in fks:
            if fk['name']:
                op.drop_constraint(fk['name'], table_name, type_='foreignkey')

    # Step 2: Alter columns to BIGINT
    _alter_columns_to_bigint()

    # Step 3: Recreate FKs
    for table_name, fks in fk_info.items():
        for fk in fks:
            if fk['name']:
                op.create_foreign_key(
                    fk['name'], table_name, fk['referred_table'],
                    fk['constrained_columns'], fk['referred_columns'],
                    ondelete=fk.get('ondelete'), onupdate=fk.get('onupdate')
                )


def _upgrade_postgresql() -> None:
    """PostgreSQL: Direct column alteration (automatically cascades to FKs)"""
    _alter_columns_to_bigint()


def _alter_columns_to_bigint():
    """Alter all ID columns from INTEGER to BIGINT"""
    # Parent tables - all primary keys are NOT NULL with autoincrement
    op.alter_column('admins', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('core_configs', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('groups', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('hosts', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('inbounds', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('user_templates', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('settings', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('system', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)

    # Mid-tier (with FKs to parents)
    op.alter_column('nodes', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('nodes', 'core_config_id', type_=sa.BigInteger(), nullable=True)
    op.alter_column('users', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('users', 'admin_id', type_=sa.BigInteger(), nullable=True)

    # Child tables
    op.alter_column('admin_usage_logs', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('admin_usage_logs', 'admin_id', type_=sa.BigInteger(), nullable=False)
    op.alter_column('node_stats', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('node_stats', 'node_id', type_=sa.BigInteger(), nullable=False)
    op.alter_column('node_usages', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('node_usages', 'node_id', type_=sa.BigInteger(), nullable=True)
    op.alter_column('node_user_usages', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('node_user_usages', 'user_id', type_=sa.BigInteger(), nullable=False)
    op.alter_column('node_user_usages', 'node_id', type_=sa.BigInteger(), nullable=True)
    op.alter_column('node_usage_reset_logs', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('node_usage_reset_logs', 'node_id', type_=sa.BigInteger(), nullable=False)
    op.alter_column('notification_reminders', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('notification_reminders', 'user_id', type_=sa.BigInteger(), nullable=False)
    op.alter_column('user_usage_logs', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('user_usage_logs', 'user_id', type_=sa.BigInteger(), nullable=True)
    op.alter_column('user_subscription_updates', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('user_subscription_updates', 'user_id', type_=sa.BigInteger(), nullable=False)
    op.alter_column('next_plans', 'id', type_=sa.BigInteger(), nullable=False, autoincrement=True)
    op.alter_column('next_plans', 'user_id', type_=sa.BigInteger(), nullable=False)
    op.alter_column('next_plans', 'user_template_id', type_=sa.BigInteger(), nullable=True)

    # Association tables
    op.alter_column('inbounds_groups_association', 'inbound_id', type_=sa.BigInteger(), nullable=False)
    op.alter_column('inbounds_groups_association', 'group_id', type_=sa.BigInteger(), nullable=False)
    op.alter_column('users_groups_association', 'user_id', type_=sa.BigInteger(), nullable=False)
    op.alter_column('users_groups_association', 'groups_id', type_=sa.BigInteger(), nullable=False)
    op.alter_column('template_group_association', 'user_template_id', type_=sa.BigInteger(), nullable=True)
    op.alter_column('template_group_association', 'group_id', type_=sa.BigInteger(), nullable=True)


def _downgrade_mysql() -> None:
    """MySQL: Drop FKs, revert to INTEGER, recreate FKs"""

    tables_with_fks = [
        'admin_usage_logs', 'users', 'nodes', 'node_stats', 'node_usages',
        'node_user_usages', 'node_usage_reset_logs', 'notification_reminders',
        'user_usage_logs', 'user_subscription_updates', 'next_plans',
        'inbounds_groups_association', 'users_groups_association', 'template_group_association',
    ]

    fk_info = {}
    for table_name in tables_with_fks:
        fks = _get_foreign_keys_for_table(table_name)
        fk_info[table_name] = fks
        for fk in fks:
            if fk['name']:
                op.drop_constraint(fk['name'], table_name, type_='foreignkey')

    _alter_columns_to_integer()

    for table_name, fks in fk_info.items():
        for fk in fks:
            if fk['name']:
                op.create_foreign_key(
                    fk['name'], table_name, fk['referred_table'],
                    fk['constrained_columns'], fk['referred_columns'],
                    ondelete=fk.get('ondelete'), onupdate=fk.get('onupdate')
                )


def _downgrade_postgresql() -> None:
    """PostgreSQL: Direct column alteration back to INTEGER"""
    _alter_columns_to_integer()


def _alter_columns_to_integer():
    """Revert all ID columns from BIGINT to INTEGER"""
    # Association tables
    op.alter_column('template_group_association', 'group_id', type_=sa.INTEGER(), nullable=True)
    op.alter_column('template_group_association', 'user_template_id', type_=sa.INTEGER(), nullable=True)
    op.alter_column('users_groups_association', 'groups_id', type_=sa.INTEGER(), nullable=False)
    op.alter_column('users_groups_association', 'user_id', type_=sa.INTEGER(), nullable=False)
    op.alter_column('inbounds_groups_association', 'group_id', type_=sa.INTEGER(), nullable=False)
    op.alter_column('inbounds_groups_association', 'inbound_id', type_=sa.INTEGER(), nullable=False)

    # Child tables
    op.alter_column('next_plans', 'user_template_id', type_=sa.INTEGER(), nullable=True)
    op.alter_column('next_plans', 'user_id', type_=sa.INTEGER(), nullable=False)
    op.alter_column('next_plans', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('user_subscription_updates', 'user_id', type_=sa.INTEGER(), nullable=False)
    op.alter_column('user_subscription_updates', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('user_usage_logs', 'user_id', type_=sa.INTEGER(), nullable=True)
    op.alter_column('user_usage_logs', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('notification_reminders', 'user_id', type_=sa.INTEGER(), nullable=False)
    op.alter_column('notification_reminders', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('node_usage_reset_logs', 'node_id', type_=sa.INTEGER(), nullable=False)
    op.alter_column('node_usage_reset_logs', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('node_user_usages', 'node_id', type_=sa.INTEGER(), nullable=True)
    op.alter_column('node_user_usages', 'user_id', type_=sa.INTEGER(), nullable=False)
    op.alter_column('node_user_usages', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('node_usages', 'node_id', type_=sa.INTEGER(), nullable=True)
    op.alter_column('node_usages', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('node_stats', 'node_id', type_=sa.INTEGER(), nullable=False)
    op.alter_column('node_stats', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('admin_usage_logs', 'admin_id', type_=sa.INTEGER(), nullable=False)
    op.alter_column('admin_usage_logs', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)

    # Mid-tier
    op.alter_column('users', 'admin_id', type_=sa.INTEGER(), nullable=True)
    op.alter_column('users', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('nodes', 'core_config_id', type_=sa.INTEGER(), nullable=True)
    op.alter_column('nodes', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)

    # Parent tables
    op.alter_column('system', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('settings', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('user_templates', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('inbounds', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('hosts', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('groups', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('core_configs', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
    op.alter_column('admins', 'id', type_=sa.INTEGER(), nullable=False, autoincrement=True)
