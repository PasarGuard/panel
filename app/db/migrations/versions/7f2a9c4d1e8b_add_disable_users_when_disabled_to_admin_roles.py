"""add disable_users_when_disabled to admin roles

Revision ID: 7f2a9c4d1e8b
Revises: 6a7e2f9c1d4b
Create Date: 2026-06-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "7f2a9c4d1e8b"
down_revision = "6a7e2f9c1d4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("admin_roles", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("disable_users_when_disabled", sa.Boolean(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    with op.batch_alter_table("admin_roles", schema=None) as batch_op:
        batch_op.drop_column("disable_users_when_disabled")
