"""add format-specific ECH fields to hosts

Revision ID: 48a6bcb8bba1
Revises: 7c4bd5128e62
Create Date: 2026-09-02 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "48a6bcb8bba1"
down_revision = "7c4bd5128e62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosts", sa.Column("mihomo_ech_config", sa.Text(), nullable=True))
    op.add_column("hosts", sa.Column("mihomo_ech_query_server_name", sa.String(length=255), nullable=True))
    op.add_column("hosts", sa.Column("sing_box_ech_config", sa.Text(), nullable=True))
    op.add_column("hosts", sa.Column("sing_box_ech_query_server_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("hosts", "sing_box_ech_query_server_name")
    op.drop_column("hosts", "sing_box_ech_config")
    op.drop_column("hosts", "mihomo_ech_query_server_name")
    op.drop_column("hosts", "mihomo_ech_config")
