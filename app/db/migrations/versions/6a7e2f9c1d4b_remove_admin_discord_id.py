"""remove admin discord id

Revision ID: 6a7e2f9c1d4b
Revises: 4b1b42d5a8c0
Create Date: 2026-05-31 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6a7e2f9c1d4b"
down_revision = "4b1b42d5a8c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("admins", schema=None) as batch_op:
        batch_op.drop_column("discord_id")


def downgrade() -> None:
    with op.batch_alter_table("admins", schema=None) as batch_op:
        batch_op.add_column(sa.Column("discord_id", sa.BigInteger(), nullable=True))
