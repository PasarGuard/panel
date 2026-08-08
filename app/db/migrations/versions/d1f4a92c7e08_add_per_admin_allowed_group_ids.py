"""add per-admin allowed group ids

Revision ID: d1f4a92c7e08
Revises: fb32155473c1
Create Date: 2026-08-08 18:20:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "d1f4a92c7e08"
down_revision = "fb32155473c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL means unrestricted, so every existing admin keeps whatever their
    # role already allows and nothing changes until the field is set.
    with op.batch_alter_table("admins", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "allowed_group_ids",
                sa.JSON().with_variant(JSONB(none_as_null=True), "postgresql"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("admins", schema=None) as batch_op:
        batch_op.drop_column("allowed_group_ids")
