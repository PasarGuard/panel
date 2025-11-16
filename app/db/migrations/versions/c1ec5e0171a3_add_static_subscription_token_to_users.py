"""add static subscription token to users

Revision ID: c1ec5e0171a3
Revises: 99076844dee6
Create Date: 2025-11-16 01:26:18.914275

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1ec5e0171a3'
down_revision = '99076844dee6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('static_token', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('use_static_token', sa.Boolean(), server_default=sa.text('0'), nullable=False))
        batch_op.create_unique_constraint('uq_users_static_token', ['static_token'])


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_static_token', type_='unique')
        batch_op.drop_column('use_static_token')
        batch_op.drop_column('static_token')
