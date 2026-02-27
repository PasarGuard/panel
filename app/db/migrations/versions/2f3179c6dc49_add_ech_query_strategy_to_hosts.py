"""add ech_query_strategy to hosts

Revision ID: 2f3179c6dc49
Revises: 116a916f1bcb
Create Date: 2026-02-24 17:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2f3179c6dc49"
down_revision = "116a916f1bcb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosts", sa.Column("ech_query_strategy", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("hosts", "ech_query_strategy")

