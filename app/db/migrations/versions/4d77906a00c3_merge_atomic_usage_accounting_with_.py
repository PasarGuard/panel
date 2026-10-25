"""merge atomic usage accounting with current dev migrations

Revision ID: 4d77906a00c3
Revises: c8d2e4f6a1b3, f2a7b9c4d610
Create Date: 2026-10-23 22:19:01.284995

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4d77906a00c3'
down_revision = ('c8d2e4f6a1b3', 'f2a7b9c4d610')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
