"""Add a subscription order group to hosts."""

import sqlalchemy as sa
from alembic import op

revision = "f17dba97c401"
down_revision = "f3a91b62d408"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosts", sa.Column("subscription_order_group", sa.String(7), nullable=True))


def downgrade() -> None:
    op.drop_column("hosts", "subscription_order_group")
