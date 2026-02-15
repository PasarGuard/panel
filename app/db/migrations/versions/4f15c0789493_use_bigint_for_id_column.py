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
    # Get the database dialect to handle MySQL vs PostgreSQL vs SQLite differently
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    
    if dialect_name == 'mysql':
        # MySQL requires dropping foreign keys before altering column types
        _upgrade_mysql()
    else:
        # PostgreSQL and SQLite can use batch operations
        _upgrade_other()


def _get_foreign_keys_for_table(table_name):
    """Get all foreign key constraints for a table"""
    bind = op.get_bind()
    inspector = inspect(bind)
    return inspector.get_foreign_keys(table_name)


def _upgrade_mysql() -> None:
    """MySQL-specific upgrade that drops and recreates foreign keys"""
    
    # Tables that have foreign keys we need to handle
    tables_with_fks = [
        'admin_usage_logs',
        'users',
        'nodes',
        'node_stats',
        'node_usages',
        'node_user_usages',
        'node_usage_reset_logs',
        'notification_reminders',
        'user_usage_logs',
        'user_subscription_updates',
        'next_plans',
        'inbounds_groups_association',
        'users_groups_association',
        'template_group_association',
    ]
    
    # Step 1: Collect and drop all foreign key constraints
    fk_info = {}  # Store FK info for recreation later
    for table_name in tables_with_fks:
        fks = _get_foreign_keys_for_table(table_name)
        fk_info[table_name] = fks
        for fk in fks:
            if fk['name']:
                op.drop_constraint(fk['name'], table_name, type_='foreignkey')
    
    # Step 2: Alter all columns to BIGINT
    # Parent tables
    op.alter_column('admins', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('core_configs', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('groups', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('hosts', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('inbounds', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('user_templates', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('settings', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('system', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    
    # Nodes (references core_configs)
    op.alter_column('nodes', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('nodes', 'core_config_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=True)
    
    # Users (references admins)
    op.alter_column('users', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('users', 'admin_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=True)
    
    # Child tables
    op.alter_column('admin_usage_logs', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('admin_usage_logs', 'admin_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=False)
    
    op.alter_column('node_stats', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('node_stats', 'node_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=False)
    
    op.alter_column('node_usages', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('node_usages', 'node_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=True)
    
    op.alter_column('node_user_usages', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('node_user_usages', 'user_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=False)
    op.alter_column('node_user_usages', 'node_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=True)
    
    op.alter_column('node_usage_reset_logs', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('node_usage_reset_logs', 'node_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=False)
    
    op.alter_column('notification_reminders', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('notification_reminders', 'user_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=False)
    
    op.alter_column('user_usage_logs', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('user_usage_logs', 'user_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=True)
    
    op.alter_column('user_subscription_updates', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('user_subscription_updates', 'user_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=False)
    
    op.alter_column('next_plans', 'id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), autoincrement=True, nullable=False)
    op.alter_column('next_plans', 'user_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=False)
    op.alter_column('next_plans', 'user_template_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=True)
    
    # Association tables
    op.alter_column('inbounds_groups_association', 'inbound_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=False)
    op.alter_column('inbounds_groups_association', 'group_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=False)
    
    op.alter_column('users_groups_association', 'user_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=False)
    op.alter_column('users_groups_association', 'groups_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=False)
    
    op.alter_column('template_group_association', 'user_template_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=True)
    op.alter_column('template_group_association', 'group_id', existing_type=sa.INTEGER(), type_=sa.BigInteger(), nullable=True)
    
    # Step 3: Recreate foreign key constraints using the saved info
    for table_name, fks in fk_info.items():
        for fk in fks:
            if fk['name']:
                op.create_foreign_key(
                    fk['name'],
                    table_name,
                    fk['referred_table'],
                    fk['constrained_columns'],
                    fk['referred_columns'],
                    ondelete=fk.get('ondelete'),
                    onupdate=fk.get('onupdate')
                )


def _upgrade_other() -> None:
    """PostgreSQL and SQLite upgrade using batch operations"""
    
    # Parent tables first
    with op.batch_alter_table('admins') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('core_configs') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('groups') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('hosts') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('inbounds') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('user_templates') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('settings') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('system') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
    
    # Nodes (references core_configs)
    with op.batch_alter_table('nodes') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
        batch_op.alter_column('core_config_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=True)
    
    # Users (references admins)
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
        batch_op.alter_column('admin_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=True)
    
    # Child tables
    with op.batch_alter_table('admin_usage_logs') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
        batch_op.alter_column('admin_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False)
    
    with op.batch_alter_table('inbounds_groups_association') as batch_op:
        batch_op.alter_column('inbound_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False)
        batch_op.alter_column('group_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False)
    
    with op.batch_alter_table('next_plans') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
        batch_op.alter_column('user_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False)
        batch_op.alter_column('user_template_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=True)
    
    with op.batch_alter_table('node_stats') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
        batch_op.alter_column('node_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False)
    
    with op.batch_alter_table('node_usage_reset_logs') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
        batch_op.alter_column('node_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False)
    
    with op.batch_alter_table('node_usages') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
        batch_op.alter_column('node_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=True)
    
    with op.batch_alter_table('node_user_usages') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
        batch_op.alter_column('user_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False)
        batch_op.alter_column('node_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=True)
    
    with op.batch_alter_table('notification_reminders') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
        batch_op.alter_column('user_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False)
    
    with op.batch_alter_table('template_group_association') as batch_op:
        batch_op.alter_column('user_template_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=True)
        batch_op.alter_column('group_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=True)
    
    with op.batch_alter_table('user_subscription_updates') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
        batch_op.alter_column('user_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False)
    
    with op.batch_alter_table('user_usage_logs') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False,
                   autoincrement=True)
        batch_op.alter_column('user_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=True)
    
    with op.batch_alter_table('users_groups_association') as batch_op:
        batch_op.alter_column('user_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False)
        batch_op.alter_column('groups_id',
                   existing_type=sa.INTEGER(),
                   type_=sa.BigInteger(),
                   existing_nullable=False)


def downgrade() -> None:
    # Get the database dialect
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    
    if dialect_name == 'mysql':
        _downgrade_mysql()
    else:
        _downgrade_other()


def _downgrade_mysql() -> None:
    """MySQL-specific downgrade"""
    
    # Tables that have foreign keys
    tables_with_fks = [
        'admin_usage_logs',
        'users',
        'nodes',
        'node_stats',
        'node_usages',
        'node_user_usages',
        'node_usage_reset_logs',
        'notification_reminders',
        'user_usage_logs',
        'user_subscription_updates',
        'next_plans',
        'inbounds_groups_association',
        'users_groups_association',
        'template_group_association',
    ]
    
    # Step 1: Collect and drop foreign keys
    fk_info = {}
    for table_name in tables_with_fks:
        fks = _get_foreign_keys_for_table(table_name)
        fk_info[table_name] = fks
        for fk in fks:
            if fk['name']:
                op.drop_constraint(fk['name'], table_name, type_='foreignkey')
    
    # Step 2: Alter columns back to INTEGER
    # Association tables
    op.alter_column('template_group_association', 'group_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=True)
    op.alter_column('template_group_association', 'user_template_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=True)
    op.alter_column('users_groups_association', 'groups_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=False)
    op.alter_column('users_groups_association', 'user_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=False)
    op.alter_column('inbounds_groups_association', 'group_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=False)
    op.alter_column('inbounds_groups_association', 'inbound_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=False)
    
    # Child tables
    op.alter_column('next_plans', 'user_template_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=True)
    op.alter_column('next_plans', 'user_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=False)
    op.alter_column('next_plans', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('user_subscription_updates', 'user_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=False)
    op.alter_column('user_subscription_updates', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('user_usage_logs', 'user_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=True)
    op.alter_column('user_usage_logs', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('notification_reminders', 'user_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=False)
    op.alter_column('notification_reminders', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('node_usage_reset_logs', 'node_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=False)
    op.alter_column('node_usage_reset_logs', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('node_user_usages', 'node_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=True)
    op.alter_column('node_user_usages', 'user_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=False)
    op.alter_column('node_user_usages', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('node_usages', 'node_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=True)
    op.alter_column('node_usages', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('node_stats', 'node_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=False)
    op.alter_column('node_stats', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('admin_usage_logs', 'admin_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=False)
    op.alter_column('admin_usage_logs', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    
    # Users and Nodes
    op.alter_column('users', 'admin_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=True)
    op.alter_column('users', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('nodes', 'core_config_id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), nullable=True)
    op.alter_column('nodes', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    
    # Parent tables
    op.alter_column('system', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('settings', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('user_templates', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('inbounds', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('hosts', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('groups', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('core_configs', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    op.alter_column('admins', 'id', existing_type=sa.BigInteger(), type_=sa.INTEGER(), autoincrement=True, nullable=False)
    
    # Step 3: Recreate foreign keys
    for table_name, fks in fk_info.items():
        for fk in fks:
            if fk['name']:
                op.create_foreign_key(
                    fk['name'],
                    table_name,
                    fk['referred_table'],
                    fk['constrained_columns'],
                    fk['referred_columns'],
                    ondelete=fk.get('ondelete'),
                    onupdate=fk.get('onupdate')
                )


def _downgrade_other() -> None:
    """PostgreSQL and SQLite downgrade using batch operations"""
    
    # Reverse order - child tables first
    with op.batch_alter_table('users_groups_association') as batch_op:
        batch_op.alter_column('groups_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False)
        batch_op.alter_column('user_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False)
    
    with op.batch_alter_table('user_usage_logs') as batch_op:
        batch_op.alter_column('user_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=True)
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('user_subscription_updates') as batch_op:
        batch_op.alter_column('user_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False)
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('template_group_association') as batch_op:
        batch_op.alter_column('group_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=True)
        batch_op.alter_column('user_template_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=True)
    
    with op.batch_alter_table('notification_reminders') as batch_op:
        batch_op.alter_column('user_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False)
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('node_user_usages') as batch_op:
        batch_op.alter_column('node_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=True)
        batch_op.alter_column('user_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False)
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('node_usages') as batch_op:
        batch_op.alter_column('node_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=True)
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('node_usage_reset_logs') as batch_op:
        batch_op.alter_column('node_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False)
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('node_stats') as batch_op:
        batch_op.alter_column('node_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False)
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('next_plans') as batch_op:
        batch_op.alter_column('user_template_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=True)
        batch_op.alter_column('user_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False)
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('inbounds_groups_association') as batch_op:
        batch_op.alter_column('group_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False)
        batch_op.alter_column('inbound_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False)
    
    with op.batch_alter_table('admin_usage_logs') as batch_op:
        batch_op.alter_column('admin_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False)
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    # Users and Nodes
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('admin_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=True)
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('nodes') as batch_op:
        batch_op.alter_column('core_config_id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=True)
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    # Parent tables
    with op.batch_alter_table('system') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('settings') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('user_templates') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('inbounds') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('hosts') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('groups') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('core_configs') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
    
    with op.batch_alter_table('admins') as batch_op:
        batch_op.alter_column('id',
                   existing_type=sa.BigInteger(),
                   type_=sa.INTEGER(),
                   existing_nullable=False,
                   autoincrement=True)
