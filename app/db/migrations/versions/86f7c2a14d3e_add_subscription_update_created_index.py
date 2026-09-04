"""add subscription update created_at index

Revision ID: 86f7c2a14d3e
Revises: 7c4bd5128e62
Create Date: 2026-09-04 00:00:00.000000

"""

from alembic import op


revision = "86f7c2a14d3e"
down_revision = "7c4bd5128e62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_user_subscription_updates_created_at",
        "user_subscription_updates",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_user_subscription_updates_created_at", table_name="user_subscription_updates")
