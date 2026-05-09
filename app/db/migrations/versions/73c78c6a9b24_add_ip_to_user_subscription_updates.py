"""add ip to user subscription updates

Revision ID: 73c78c6a9b24
Revises: af2d644dda44
Create Date: 2026-05-06 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "73c78c6a9b24"
down_revision = "af2d644dda44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_subscription_updates", sa.Column("ip", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_subscription_updates", schema=None) as batch_op:
        batch_op.drop_column("ip")
