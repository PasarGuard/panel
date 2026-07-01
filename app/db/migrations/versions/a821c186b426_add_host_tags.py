"""add host tags

Revision ID: a821c186b426
Revises: a3b4c5d6e7f8
Create Date: 2026-07-01 19:12:23.382022

"""

from alembic import op
import sqlalchemy as sa
import app.db.compiles_types


revision = "a821c186b426"
down_revision = "b6c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "host_tags",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("color", sa.String(length=32), nullable=False),
        sa.Column("id", app.db.compiles_types.SqliteCompatibleBigInteger(), autoincrement=True, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_host_tags")),
        sa.UniqueConstraint("name", name=op.f("uq_host_tags_name")),
    )
    op.create_table(
        "hosts_tags_association",
        sa.Column("host_id", app.db.compiles_types.SqliteCompatibleBigInteger(), nullable=False),
        sa.Column("tag_id", app.db.compiles_types.SqliteCompatibleBigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["host_id"], ["hosts.id"], name=op.f("fk_hosts_tags_association_host_id_hosts"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"], ["host_tags.id"], name=op.f("fk_hosts_tags_association_tag_id_host_tags"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("host_id", "tag_id", name=op.f("pk_hosts_tags_association")),
    )


def downgrade() -> None:
    op.drop_table("hosts_tags_association")
    op.drop_table("host_tags")
