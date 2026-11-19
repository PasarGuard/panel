"""add per-admin host remark and disabled overrides

Revision ID: 5e7b3a9c1d42
Revises: c8d2e4f6a1b3
"""

import sqlalchemy as sa
from alembic import op

from app.db.compiles_types import SqliteCompatibleBigInteger

revision = "5e7b3a9c1d42"
down_revision = "c8d2e4f6a1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_host_overrides",
        sa.Column("id", SqliteCompatibleBigInteger(), autoincrement=True, nullable=False),
        sa.Column("admin_id", SqliteCompatibleBigInteger(), nullable=False),
        sa.Column("host_id", SqliteCompatibleBigInteger(), nullable=False),
        sa.Column("remark", sa.String(length=256), nullable=True),
        sa.Column("is_disabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["admin_id"], ["admins.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("admin_id", "host_id", name="uq_admin_host_overrides_admin_id_host_id"),
    )
    op.create_index(op.f("ix_admin_host_overrides_host_id"), "admin_host_overrides", ["host_id"], unique=False)


def downgrade() -> None:
    # Dropping the table drops its indexes; MySQL refuses to drop the host_id index alone while the FK uses it
    op.drop_table("admin_host_overrides")
