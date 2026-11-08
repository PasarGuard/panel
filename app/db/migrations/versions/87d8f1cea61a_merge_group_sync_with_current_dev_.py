"""merge group sync with current dev migrations

Revision ID: 87d8f1cea61a
Revises: c8d2e4f6a1b3, f2d6a8b93107
Create Date: 2026-10-23 22:12:29.299369

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '87d8f1cea61a'
down_revision = ('c8d2e4f6a1b3', 'f2d6a8b93107')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
