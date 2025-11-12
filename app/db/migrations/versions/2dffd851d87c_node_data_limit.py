"""node data limit

Revision ID: 2dffd851d87c
Revises: 797420faec8d
Create Date: 2025-11-12 01:02:04.732358

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2dffd851d87c'
down_revision = '797420faec8d'
branch_labels = None
depends_on = None

# DataLimitResetStrategy enum configuration
old_enum_name = "userdatalimitresetstrategy"
new_enum_name = "datalimitresetstrategy"
enum_values = ('no_reset', 'day', 'week', 'month', 'year')

new_type = sa.Enum(*enum_values, name=new_enum_name)

# NodeStatus enum configuration
node_status_enum_name = "nodestatus"
node_status_temp_enum_name = "temp_nodestatus"
old_node_status_values = ('connected', 'connecting', 'error', 'disabled')
new_node_status_values = ('connected', 'connecting', 'error', 'disabled', 'limited')
downgrade_node_status = ("limited", "disabled")  # Convert limited -> disabled on downgrade

old_node_status_type = sa.Enum(*old_node_status_values, name=node_status_enum_name)
new_node_status_type = sa.Enum(*new_node_status_values, name=node_status_enum_name)
temp_node_status_type = sa.Enum(*new_node_status_values, name=node_status_temp_enum_name)

# Table definition for status updates
nodes_table = sa.sql.table(
    'nodes',
    sa.Column('status', new_node_status_type, nullable=False)
)


def upgrade() -> None:
    bind = op.get_bind()

    # Create node_usage_reset_logs table
    op.create_table('node_usage_reset_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('node_id', sa.Integer(), nullable=False),
        sa.Column('uplink', sa.BigInteger(), nullable=False),
        sa.Column('downlink', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['node_id'], ['nodes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Update NodeStatus enum to add 'limited' value
    temp_node_status_type.create(op.get_bind(), checkfirst=False)

    with op.batch_alter_table('nodes') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=old_node_status_type,
            type_=temp_node_status_type,
            existing_nullable=False,
            postgresql_using="status::text::temp_nodestatus"
        )

    old_node_status_type.drop(op.get_bind(), checkfirst=False)
    new_node_status_type.create(op.get_bind(), checkfirst=False)

    with op.batch_alter_table('nodes') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=temp_node_status_type,
            type_=new_node_status_type,
            existing_nullable=False,
            postgresql_using="status::text::nodestatus"
        )

    temp_node_status_type.drop(op.get_bind(), checkfirst=False)

    # Add columns to nodes table
    op.add_column('nodes', sa.Column('data_limit', sa.BigInteger(), nullable=True))

    # Rename enum type BEFORE adding the column (PostgreSQL only)
    if bind.dialect.name == "postgresql":
        op.execute(f"ALTER TYPE {old_enum_name} RENAME TO {new_enum_name};")
    # For MySQL/SQLite: No-op (enum name is irrelevant)

    op.add_column('nodes', sa.Column('data_limit_reset_strategy', new_type, nullable=False, server_default='no_reset'))
    op.add_column('nodes', sa.Column('reset_time', sa.Integer(), server_default=sa.text('-1'), nullable=False))


def downgrade() -> None:
    bind = op.get_bind()

    # Drop nodes columns
    op.drop_column('nodes', 'reset_time')
    op.drop_column('nodes', 'data_limit_reset_strategy')
    op.drop_column('nodes', 'data_limit')

    # Reverse the enum rename (PostgreSQL only)
    if bind.dialect.name == "postgresql":
        op.execute(f"ALTER TYPE {new_enum_name} RENAME TO {old_enum_name};")
    # For MySQL/SQLite: No-op

    # Convert any 'limited' status to 'disabled' before downgrading enum
    op.execute(
        nodes_table
        .update()
        .where(nodes_table.c.status == downgrade_node_status[0])
        .values(status=downgrade_node_status[1])
    )

    # Reverse NodeStatus enum changes
    temp_node_status_type.create(op.get_bind(), checkfirst=False)

    with op.batch_alter_table('nodes') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=new_node_status_type,
            type_=temp_node_status_type,
            existing_nullable=False,
            postgresql_using="status::text::temp_nodestatus"
        )

    new_node_status_type.drop(op.get_bind(), checkfirst=False)
    old_node_status_type.create(op.get_bind(), checkfirst=False)

    with op.batch_alter_table('nodes') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=temp_node_status_type,
            type_=old_node_status_type,
            existing_nullable=False,
            postgresql_using="status::text::nodestatus"
        )

    temp_node_status_type.drop(op.get_bind(), checkfirst=False)

    # Drop node_usage_reset_logs table
    op.drop_table('node_usage_reset_logs')
