"""add wireguard_overrides json to hosts

Revision ID: c8f4a1b2d3e5
Revises: 6d0f9e5f2b87
Create Date: 2026-04-03 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "c8f4a1b2d3e5"
down_revision = "6d0f9e5f2b87"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosts", sa.Column("wireguard_overrides", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("hosts", "wireguard_overrides")
