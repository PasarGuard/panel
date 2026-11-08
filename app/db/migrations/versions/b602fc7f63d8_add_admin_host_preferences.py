"""add per-admin host display preferences

Revision ID: b602fc7f63d8
Revises: c7d2e9a4b1f3
Create Date: 2026-11-08 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b602fc7f63d8"
down_revision = "c7d2e9a4b1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("admins", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "host_preferences",
                sa.JSON().with_variant(postgresql.JSONB(none_as_null=True, astext_type=sa.Text()), "postgresql"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("admins", schema=None) as batch_op:
        batch_op.drop_column("host_preferences")
