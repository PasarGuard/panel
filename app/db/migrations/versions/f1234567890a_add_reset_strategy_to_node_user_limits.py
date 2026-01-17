"""add reset strategy to node user limits

Revision ID: f1234567890a
Revises: e3879a8dfdab
Create Date: 2026-01-16 16:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'f1234567890a'
down_revision = 'e3879a8dfdab'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add data_limit_reset_strategy column with default value
    op.add_column('node_user_limits', 
        sa.Column('data_limit_reset_strategy', sa.String(), server_default='no_reset', nullable=False)
    )
    
    # Add reset_time column with default value
    op.add_column('node_user_limits', 
        sa.Column('reset_time', sa.Integer(), server_default=text('-1'), nullable=False)
    )


def downgrade() -> None:
    # Remove the added columns
    op.drop_column('node_user_limits', 'reset_time')
    op.drop_column('node_user_limits', 'data_limit_reset_strategy')
