"""add plugin_settings table

Revision ID: d4e7a9c2b5f1
Revises: c8d2e4f6a1b3
Create Date: 2026-10-23 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d4e7a9c2b5f1"
down_revision = "c8d2e4f6a1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plugin_settings",
        sa.Column("plugin_id", sa.String(length=64), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("plugin_id", name=op.f("pk_plugin_settings")),
    )


def downgrade() -> None:
    op.drop_table("plugin_settings")
