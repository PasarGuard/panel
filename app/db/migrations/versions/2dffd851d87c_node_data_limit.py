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

# Enum configuration
old_enum_name = "userdatalimitresetstrategy"
new_enum_name = "datalimitresetstrategy"
enum_values = ('no_reset', 'day', 'week', 'month', 'year')

new_type = sa.Enum(*enum_values, name=new_enum_name)


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

    # Drop node_usage_reset_logs table
    op.drop_table('node_usage_reset_logs')
