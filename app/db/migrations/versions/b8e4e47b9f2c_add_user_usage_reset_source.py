"""add user usage reset source

Revision ID: b8e4e47b9f2c
Revises: 9e0d7a1c4b52
Create Date: 2026-05-10 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b8e4e47b9f2c"
down_revision = "9e0d7a1c4b52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_usage_logs",
        sa.Column("reset_source", sa.String(length=32), nullable=False, server_default="legacy"),
    )
    op.create_index(
        "ix_user_usage_logs_user_id_source_reset_at",
        "user_usage_logs",
        ["user_id", "reset_source", "reset_at"],
    )
    # Historical rows and rows written by an older process during a rolling
    # upgrade may represent manual,
    # scheduled, or next-plan resets.  Do not guess: treating them as
    # scheduled would let an old manual reset postpone the next cycle.
    # ``legacy`` keeps those rows distinguishable so the scheduler can use the
    # latest one only as a transitional anchor until a trusted reset exists.
    op.execute("UPDATE user_usage_logs SET reset_source = 'legacy'")


def downgrade() -> None:
    op.drop_index("ix_user_usage_logs_user_id_source_reset_at", table_name="user_usage_logs")
    op.drop_column("user_usage_logs", "reset_source")
