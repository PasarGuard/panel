"""add custom variables to admins

Revision ID: d4f8c1b2a9e3
Revises: a3b4c5d6e7f8
Create Date: 2026-06-17 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "d4f8c1b2a9e3"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("admins") as batch_op:
        batch_op.add_column(sa.Column("custom_variables", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("admins") as batch_op:
        batch_op.drop_column("custom_variables")
