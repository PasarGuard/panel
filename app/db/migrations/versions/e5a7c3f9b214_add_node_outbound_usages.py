"""add node outbound usages

Revision ID: e5a7c3f9b214
Revises: b849540d85bb
Create Date: 2026-10-29 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

from app.db.compiles_types import CaseSensitiveString, SqliteCompatibleBigInteger

revision = "e5a7c3f9b214"
down_revision = "b849540d85bb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "node_outbound_usages",
        sa.Column("id", SqliteCompatibleBigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("node_id", SqliteCompatibleBigInteger(), nullable=False),
        sa.Column("outbound_tag", CaseSensitiveString(length=256), nullable=False),
        sa.Column("uplink", sa.BigInteger(), nullable=False),
        sa.Column("downlink", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["nodes.id"],
            name=op.f("fk_node_outbound_usages_node_id_nodes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_node_outbound_usages")),
        sa.UniqueConstraint("created_at", "node_id", "outbound_tag", name=op.f("uq_node_outbound_usages_created_at")),
    )
    op.create_index(
        "ix_node_outbound_usages_node_id_created_at",
        "node_outbound_usages",
        ["node_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    # Dropping the table drops its indexes; MySQL refuses to drop the node_id index first (the foreign key needs it)
    op.drop_table("node_outbound_usages")
