"""add user usage reset source

Revision ID: b8e4e47b9f2c
Revises: 73c78c6a9b24
Create Date: 2026-05-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b8e4e47b9f2c"
down_revision = "73c78c6a9b24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_usage_logs",
        sa.Column("reset_source", sa.String(length=32), nullable=False, server_default="manual"),
    )
    op.execute("UPDATE user_usage_logs SET reset_source = 'scheduled'")


def downgrade() -> None:
    op.drop_column("user_usage_logs", "reset_source")
