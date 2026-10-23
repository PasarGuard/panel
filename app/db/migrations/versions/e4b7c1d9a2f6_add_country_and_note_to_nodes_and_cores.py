"""add country code and note to nodes, note to core configs

Revision ID: e4b7c1d9a2f6
Revises: c8d2e4f6a1b3
Create Date: 2026-10-23 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "e4b7c1d9a2f6"
down_revision = "c8d2e4f6a1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable country code and note columns for nodes and a note column for core configs."""
    op.add_column("nodes", sa.Column("country_code", sa.String(length=2), nullable=True))
    op.add_column("nodes", sa.Column("note", sa.String(length=500), nullable=True))
    op.add_column("core_configs", sa.Column("note", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Remove the country code and note columns."""
    with op.batch_alter_table("core_configs") as batch_op:
        batch_op.drop_column("note")
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_column("note")
        batch_op.drop_column("country_code")
