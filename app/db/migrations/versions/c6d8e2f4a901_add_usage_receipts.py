"""Add durable usage receipt slots.

Revision ID: c6d8e2f4a901
Revises: b4c7e8f1a2d3
"""
from alembic import op
import sqlalchemy as sa

revision = "c6d8e2f4a901"
down_revision = "b4c7e8f1a2d3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usage_receipts",
        sa.Column("node_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("receipt_id", sa.String(36), nullable=False),
        sa.Column("payload", sa.JSON(none_as_null=True), nullable=True),
        sa.PrimaryKeyConstraint("node_id", "kind"),
    )


def downgrade():
    # Drain usage_receipts before downgrading; pending traffic cannot be represented by the old schema.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM usage_receipts WHERE payload IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade with pending usage receipts")
    op.drop_table("usage_receipts")
