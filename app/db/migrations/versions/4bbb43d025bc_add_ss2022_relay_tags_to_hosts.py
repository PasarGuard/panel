"""add ss2022_relay_inbound_tags to hosts

Revision ID: 4bbb43d025bc
Revises: 8350e561677a
Create Date: 2025-10-31
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4bbb43d025bc'
down_revision = '8350e561677a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('hosts', sa.Column('ss2022_relay_inbound_tags', sa.String(length=2048), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('hosts') as batch_op:
        batch_op.drop_column('ss2022_relay_inbound_tags')


