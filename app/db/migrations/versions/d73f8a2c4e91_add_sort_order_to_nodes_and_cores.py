"""add sort order to nodes and core configs

Revision ID: d73f8a2c4e91
Revises: 7c4bd5128e62
Create Date: 2026-09-07 13:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d73f8a2c4e91"
down_revision = "7c4bd5128e62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("nodes", "core_configs"):
        op.add_column(table_name, sa.Column("sort_order", sa.Integer(), nullable=True))
        op.execute(sa.text(f"UPDATE {table_name} SET sort_order = id"))
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "sort_order",
                existing_type=sa.Integer(),
                nullable=False,
                server_default="0",
            )


def downgrade() -> None:
    for table_name in ("core_configs", "nodes"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("sort_order")
