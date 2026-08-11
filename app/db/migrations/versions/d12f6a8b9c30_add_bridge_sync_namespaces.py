"""Add stable Bridge node and user sync namespaces.

Rollout contract: run this migration while writes are quiesced, before starting
application code that reads ``bridge_id``/``sync_id``. The nullable add plus
backfill keeps the DDL portable; the explicit NULL check prevents a concurrent
legacy insert from being silently promoted into an invalid namespace.

Revision ID: d12f6a8b9c30
Revises: a8c2d491e705
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op

revision = "d12f6a8b9c30"
down_revision = "a8c2d491e705"
branch_labels = None
depends_on = None


def _backfill_legacy_namespace(connection, table: str, column: str) -> None:
    # Preserve the namespace already used by running Bridge/core processes and
    # NATS KV. Newly created ORM rows use UUID defaults, so a later reused
    # numeric database id cannot inherit this incarnation's state or stats.
    table_ref = sa.table(table, sa.column("id"), sa.column(column))
    connection.execute(
        sa.update(table_ref)
        .where(table_ref.c[column].is_(None))
        .values({column: sa.cast(table_ref.c.id, sa.String(36))})
    )


def _assert_backfill_complete(connection, table: str, column: str) -> None:
    table_ref = sa.table(table, sa.column(column))
    remaining = connection.scalar(
        sa.select(sa.func.count()).select_from(table_ref).where(table_ref.c[column].is_(None))
    )
    if remaining:
        raise RuntimeError(
            f"{table}.{column} backfill left {remaining} NULL row(s); stop legacy writers and rerun the migration"
        )


def upgrade() -> None:
    connection = op.get_bind()
    op.add_column("nodes", sa.Column("bridge_id", sa.String(length=36), nullable=True))
    op.add_column("users", sa.Column("sync_id", sa.String(length=36), nullable=True))
    _backfill_legacy_namespace(connection, "nodes", "bridge_id")
    _backfill_legacy_namespace(connection, "users", "sync_id")
    _assert_backfill_complete(connection, "nodes", "bridge_id")
    _assert_backfill_complete(connection, "users", "sync_id")

    with op.batch_alter_table("nodes") as batch_op:
        batch_op.alter_column("bridge_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_unique_constraint("uq_nodes_bridge_id", ["bridge_id"])
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("sync_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_unique_constraint("uq_users_sync_id", ["sync_id"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_sync_id", type_="unique")
        batch_op.drop_column("sync_id")
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_constraint("uq_nodes_bridge_id", type_="unique")
        batch_op.drop_column("bridge_id")
