"""Replace the single receipt slot with independent durable receipt identities."""

from alembic import op
import sqlalchemy as sa

revision = "d8f1a7b9c203"
down_revision = "c6d8e2f4a901"
branch_labels = None
depends_on = None


def upgrade():
    ledger = op.create_table(
        "usage_receipt_ledger",
        sa.Column("node_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("receipt_id", sa.String(36), nullable=False),
        sa.Column("processed", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("payload", sa.JSON(none_as_null=True), nullable=True),
        sa.PrimaryKeyConstraint("node_id", "kind", "receipt_id"),
    )
    old = sa.table(
        "usage_receipts",
        sa.column("node_id", sa.BigInteger()),
        sa.column("kind", sa.String(16)),
        sa.column("receipt_id", sa.String(36)),
        sa.column("payload", sa.JSON(none_as_null=True)),
    )
    # Preserve pending payloads AND applied tombstones, including ambiguous commits.
    op.execute(
        ledger.insert().from_select(
            ["node_id", "kind", "receipt_id", "processed", "payload"],
            sa.select(old.c.node_id, old.c.kind, old.c.receipt_id, old.c.payload.is_(None), old.c.payload)
            .where(old.c.receipt_id != ""),
        )
    )
    op.create_index("ix_usage_ledger_pending", "usage_receipt_ledger", ["kind", "processed", "node_id"])
    op.drop_table("usage_receipts")


def downgrade():
    # Old slots cannot represent multiple IDs. Dropping even an applied ID permits
    # an old in-flight RPC response to charge that receipt again after rollback.
    if op.get_bind().execute(sa.text("SELECT 1 FROM usage_receipt_ledger LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade a nonempty usage receipt ledger")
    op.create_table(
        "usage_receipts",
        sa.Column("node_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("receipt_id", sa.String(36), nullable=False),
        sa.Column("payload", sa.JSON(none_as_null=True), nullable=True),
        sa.PrimaryKeyConstraint("node_id", "kind"),
    )
    op.drop_index("ix_usage_ledger_pending", table_name="usage_receipt_ledger")
    op.drop_table("usage_receipt_ledger")
