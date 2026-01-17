"""add_node_user_limits_to_template

Revision ID: f1234567890c
Revises: f1234567890b
Create Date: 2026-01-16 22:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql, postgresql, sqlite

# revision identifiers, used by Alembic.
revision = 'f1234567890c'
down_revision = 'f1234567890b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add node_user_limits JSON column to user_templates table
    with op.batch_alter_table('user_templates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('node_user_limits', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove node_user_limits column from user_templates table
    with op.batch_alter_table('user_templates', schema=None) as batch_op:
        batch_op.drop_column('node_user_limits')
