"""add backend type to core configs

Revision ID: 6d0f9e5f2b87
Revises: 145c22ab174f
Create Date: 2026-04-02 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6d0f9e5f2b87"
down_revision = "145c22ab174f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "core_configs",
        sa.Column("backend_type", sa.String(length=32), nullable=False, server_default="xray"),
    )
    op.execute("UPDATE core_configs SET backend_type = 'xray' WHERE backend_type IS NULL")


def downgrade() -> None:
    op.drop_column("core_configs", "backend_type")
