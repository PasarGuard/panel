"""api key request limit

Revision ID: 1a2b3c4d5e6f
Revises: 7c4bd5128e62
Create Date: 2026-08-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1a2b3c4d5e6f'
down_revision = '7c4bd5128e62'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.add_column(sa.Column("max_requests", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("request_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("delete_on_limit", sa.Boolean(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.drop_column("delete_on_limit")
        batch_op.drop_column("request_count")
        batch_op.drop_column("max_requests")
