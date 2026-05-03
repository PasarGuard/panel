"""merge hwid device limit and node proxy url heads

Revision ID: a5790b474dfe
Revises: af2d644dda44, b2c3d4e5f6a7
Create Date: 2026-05-03 11:29:59.130761

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5790b474dfe'
down_revision = ('af2d644dda44', 'b2c3d4e5f6a7')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
