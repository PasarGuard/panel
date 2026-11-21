"""Inbound usage coefficient (Usage Ratio per inbound).

Revision ID: a4c7e91b6d20
Revises: f3a91b62d408
"""

import sqlalchemy as sa
from alembic import op

revision = "a4c7e91b6d20"
down_revision = "f3a91b62d408"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbounds",
        sa.Column("usage_coefficient", sa.Float(), nullable=False, server_default=sa.text("1.0")),
    )


def downgrade() -> None:
    op.drop_column("inbounds", "usage_coefficient")
