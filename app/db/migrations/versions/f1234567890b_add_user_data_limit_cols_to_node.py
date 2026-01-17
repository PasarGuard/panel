"""add user data limit cols to node

Revision ID: f1234567890b
Revises: f1234567890a
Create Date: 2026-01-16 10:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1234567890b'
down_revision = 'f1234567890a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('nodes', sa.Column('user_data_limit', sa.BigInteger(), server_default=sa.text('0'), nullable=False))
    op.add_column('nodes', sa.Column('user_data_limit_reset_strategy', sa.Enum('no_reset', 'day', 'week', 'month', 'year', name='datalimitresetstrategy'), server_default='no_reset', nullable=False))
    op.add_column('nodes', sa.Column('user_reset_time', sa.Integer(), server_default=sa.text('-1'), nullable=False))


def downgrade() -> None:
    op.drop_column('nodes', 'user_reset_time')
    op.drop_column('nodes', 'user_data_limit_reset_strategy')
    op.drop_column('nodes', 'user_data_limit')
