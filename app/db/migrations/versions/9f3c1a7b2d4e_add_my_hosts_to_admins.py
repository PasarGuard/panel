"""add my_hosts to admins

Revision ID: 9f3c1a7b2d4e
Revises: c8d2e4f6a1b3
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op

revision = '9f3c1a7b2d4e'
down_revision = 'c8d2e4f6a1b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('admins', sa.Column('my_hosts', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('admins', 'my_hosts')
