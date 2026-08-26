"""add user subscription updates composite index

Revision ID: 7c4bd5128e62
Revises: 6a9fff8290b9
Create Date: 2026-08-26 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7c4bd5128e62'
down_revision = '6a9fff8290b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create concurrent index on user_id and created_at (DESC) for user_subscription_updates table
    op.execute('CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_subscription_updates_user_created ON user_subscription_updates (user_id, created_at DESC);')


def downgrade() -> None:
    # Drop the composite index
    op.drop_index('idx_user_subscription_updates_user_created', table_name='user_subscription_updates')