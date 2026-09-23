"""Mark historical usage rows that contain a whole UTC day.

Revision ID: a72c9d84e601
Revises: b4c7e8f1a2d3
"""

import sqlalchemy as sa
from alembic import op

revision = "a72c9d84e601"
down_revision = "b4c7e8f1a2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("node_user_usages", "node_usages"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("is_daily", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        op.create_index(f"ix_{table}_is_daily_created_at", table, ["is_daily", "created_at"])


def downgrade() -> None:
    for table in ("node_user_usages", "node_usages"):
        op.drop_index(f"ix_{table}_is_daily_created_at", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_column("is_daily")
