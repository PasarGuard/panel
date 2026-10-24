"""Store personal host preferences per admin.

Revision ID: d21f6a8c904e
Revises: c8d2e4f6a1b3
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d21f6a8c904e"
down_revision = "c8d2e4f6a1b3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "admins", sa.Column("host_preferences", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True)
    )


def downgrade():
    op.drop_column("admins", "host_preferences")
