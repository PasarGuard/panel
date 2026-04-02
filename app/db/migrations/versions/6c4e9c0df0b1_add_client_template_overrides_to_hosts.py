"""add client template overrides to hosts

Revision ID: 6c4e9c0df0b1
Revises: 145c22ab174f
Create Date: 2026-04-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6c4e9c0df0b1"
down_revision = "145c22ab174f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("hosts") as batch_op:
        batch_op.add_column(sa.Column("client_template_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("hosts") as batch_op:
        batch_op.drop_column("client_template_ids")
