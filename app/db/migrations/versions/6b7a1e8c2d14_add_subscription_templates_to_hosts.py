"""add subscription_templates json to hosts

Revision ID: 6b7a1e8c2d14
Revises: c8f4a1b2d3e5
Create Date: 2026-04-07 20:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "6b7a1e8c2d14"
down_revision = "c8f4a1b2d3e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosts", sa.Column("subscription_templates", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("hosts", "subscription_templates")
