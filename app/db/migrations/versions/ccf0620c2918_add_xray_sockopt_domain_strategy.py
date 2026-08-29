"""add xray sockopt domain strategy to hosts

Revision ID: ccf0620c2918
Revises: 7c4bd5128e62
Create Date: 2026-08-27 03:40:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ccf0620c2918"
down_revision = "7c4bd5128e62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("hosts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "xray_sockopt_domain_strategy",
                sa.String(length=16),
                server_default="AsIs",
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("hosts", schema=None) as batch_op:
        batch_op.drop_column("xray_sockopt_domain_strategy")
