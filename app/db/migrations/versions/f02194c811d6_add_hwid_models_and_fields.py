"""Add HWID support

Revision ID: f02194c811d6
Revises: 73c78c6a9b24
Create Date: 2026-05-14 14:23:22.927015

"""
from alembic import op
import sqlalchemy as sa
import app.db.compiles_types


# revision identifiers, used by Alembic.
revision = 'f02194c811d6'
down_revision = '73c78c6a9b24'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_hwids',
        sa.Column('id', app.db.compiles_types.SqliteCompatibleBigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', app.db.compiles_types.SqliteCompatibleBigInteger(), nullable=False),
        sa.Column('hwid', sa.String(length=256), nullable=False),
        sa.Column('device_os', sa.String(length=256), nullable=True),
        sa.Column('os_version', sa.String(length=128), nullable=True),
        sa.Column('device_model', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_hwids_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_user_hwids')),
        sa.UniqueConstraint('user_id', 'hwid', name=op.f('uq_user_hwids_user_id')),
    )
    with op.batch_alter_table('user_hwids', schema=None) as batch_op:
        batch_op.create_index('ix_user_hwids_user_id', ['user_id'], unique=False)
        batch_op.create_index('ix_user_hwids_hwid', ['hwid'], unique=False)
        batch_op.create_index('ix_user_hwids_created_at', ['created_at'], unique=False)
        batch_op.create_index('ix_user_hwids_last_used_at', ['last_used_at'], unique=False)

    # Fixed MySQL JSON default: Add as nullable, update, then set NOT NULL
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hwid', sa.JSON(), nullable=True))
    
    op.execute("UPDATE settings SET hwid = '{}'")
    
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.alter_column('hwid', type_=sa.JSON(), nullable=False)

    with op.batch_alter_table('user_subscription_updates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hwid', sa.String(length=256), nullable=True))

    with op.batch_alter_table('user_templates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hwid_limit', sa.BigInteger(), nullable=True))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hwid_limit', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('hwid_limit')

    with op.batch_alter_table('user_templates', schema=None) as batch_op:
        batch_op.drop_column('hwid_limit')

    with op.batch_alter_table('user_subscription_updates', schema=None) as batch_op:
        batch_op.drop_column('hwid')

    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_column('hwid')

    with op.batch_alter_table('user_hwids', schema=None) as batch_op:
        batch_op.drop_index('ix_user_hwids_last_used_at')
        batch_op.drop_index('ix_user_hwids_created_at')
        batch_op.drop_index('ix_user_hwids_hwid')
        batch_op.drop_index('ix_user_hwids_user_id')

    op.drop_table('user_hwids')
