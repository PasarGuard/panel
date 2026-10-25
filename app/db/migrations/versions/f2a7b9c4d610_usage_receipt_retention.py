"""Retain applied/ACK timestamps and fence collectors across receipt cleanup."""

from alembic import op
import sqlalchemy as sa

revision = "f2a7b9c4d610"
down_revision = "e9c3b6a71204"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usage_receipt_ledger", sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("usage_receipt_ledger", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_usage_ledger_retention", "usage_receipt_ledger", ["processed", "acknowledged_at", "applied_at"]
    )
    op.create_table(
        "usage_streams",
        sa.Column("node_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("collection_epoch", sa.String(36), nullable=False),
        sa.PrimaryKeyConstraint("node_id", "kind"),
    )
    # Existing tombstones have no proof of node ACK; never infer one from age.


def downgrade():
    # Older collectors cannot enforce the fence protecting deleted receipt IDs.
    if op.get_bind().execute(sa.text("SELECT 1 FROM usage_streams LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade initialized usage collection fences")
    op.drop_table("usage_streams")
    op.drop_index("ix_usage_ledger_retention", table_name="usage_receipt_ledger")
    op.drop_column("usage_receipt_ledger", "acknowledged_at")
    op.drop_column("usage_receipt_ledger", "applied_at")
