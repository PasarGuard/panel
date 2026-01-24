"""add ip_limit to users and user_templates

Revision ID: a1b2c3d4e5f6
Revises: ee97c01bfbaf
Create Date: 2026-01-24 13:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "ee97c01bfbaf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("ip_limit", sa.Integer(), nullable=True))

    with op.batch_alter_table("user_templates") as batch_op:
        batch_op.add_column(sa.Column("ip_limit", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("ip_limit")

    with op.batch_alter_table("user_templates") as batch_op:
        batch_op.drop_column("ip_limit")
