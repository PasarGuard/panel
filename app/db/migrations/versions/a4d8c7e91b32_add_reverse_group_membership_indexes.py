"""add reverse group membership indexes

Revision ID: a4d8c7e91b32
Revises: 6a9fff8290b9
Create Date: 2026-08-14 15:00:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "a4d8c7e91b32"
down_revision = "6a9fff8290b9"
branch_labels = None
depends_on = None


INDEXES = (
    (
        "ix_inbounds_groups_association_group_id_inbound_id",
        "inbounds_groups_association",
        ["group_id", "inbound_id"],
    ),
    (
        "ix_users_groups_association_groups_id_user_id",
        "users_groups_association",
        ["groups_id", "user_id"],
    ),
)


def _create_indexes(*, concurrently: bool) -> None:
    for name, table_name, columns in INDEXES:
        op.create_index(
            name,
            table_name,
            columns,
            unique=False,
            postgresql_concurrently=concurrently,
        )


def _drop_indexes(*, concurrently: bool) -> None:
    for name, table_name, _ in reversed(INDEXES):
        op.drop_index(
            name,
            table_name=table_name,
            postgresql_concurrently=concurrently,
        )


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # A normal PostgreSQL index build blocks membership writes. These tables
        # can contain millions of rows, so keep live installations writable.
        with op.get_context().autocommit_block():
            _create_indexes(concurrently=True)
        return

    # InnoDB creates secondary indexes online by default. SQLite needs the
    # regular form and is normally used for smaller, single-node deployments.
    _create_indexes(concurrently=False)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            _drop_indexes(concurrently=True)
        return

    _drop_indexes(concurrently=False)
