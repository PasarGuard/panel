"""Add managed WARP outbounds and independent node profiles."""

import sqlalchemy as sa
from alembic import op

from app.db.compiles_types import SqliteCompatibleBigInteger

revision = "c18e4d7a9b32"
down_revision = "b4c7e8f1a2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("core_configs", sa.Column("warp_outbound_tag", sa.String(256), nullable=True))
    op.create_table(
        "node_warp_profiles",
        sa.Column("node_id", SqliteCompatibleBigInteger(), nullable=False),
        sa.Column("settings", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_core_id", SqliteCompatibleBigInteger(), nullable=True),
        sa.Column("applied_tag", sa.String(256), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("node_id"),
    )


def downgrade() -> None:
    op.drop_table("node_warp_profiles")
    op.drop_column("core_configs", "warp_outbound_tag")
