"""add coordination locks

Revision ID: 9e2a1d0f7c3b
Revises: 8e2f1a9c4b70
Create Date: 2026-09-08 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9e2a1d0f7c3b"
down_revision = "8e2f1a9c4b70"
branch_labels = None
depends_on = None

GROUP_POLICY_LOCK_NAME = "group_policy"


def upgrade() -> None:
    coordination_locks = op.create_table(
        "coordination_locks",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_coordination_locks")),
    )
    op.bulk_insert(coordination_locks, [{"name": GROUP_POLICY_LOCK_NAME}])


def downgrade() -> None:
    op.drop_table("coordination_locks")
