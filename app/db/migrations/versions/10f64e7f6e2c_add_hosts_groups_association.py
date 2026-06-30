"""add hosts_groups_association

Revision ID: 10f64e7f6e2c
Revises: a3b4c5d6e7f8, b6c9d0e1f2a3
Create Date: 2026-06-30 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

from app.db.compiles_types import SqliteCompatibleBigInteger

# revision identifiers, used by Alembic.
revision = "10f64e7f6e2c"
down_revision = ("a3b4c5d6e7f8", "b6c9d0e1f2a3")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosts_groups_association",
        sa.Column(
            "host_id",
            SqliteCompatibleBigInteger,
            sa.ForeignKey("hosts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "group_id",
            SqliteCompatibleBigInteger,
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("hosts_groups_association")
