"""drop is_sudo from admins

Revision ID: b1e4f9a2c3d5
Revises: 66c38b8a687a
Create Date: 2026-05-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b1e4f9a2c3d5'
down_revision = '66c38b8a687a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('admins', schema=None) as batch_op:
        batch_op.drop_column('is_sudo')


def downgrade() -> None:
    with op.batch_alter_table('admins', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_sudo', sa.Boolean(), server_default='0', nullable=False))
    # Backfill from role: administrator (id=2) -> is_sudo=true, others -> is_sudo=false
    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect == "postgresql":
        conn.execute(sa.text("UPDATE admins SET is_sudo = true WHERE role_id = 2"))
        conn.execute(sa.text("UPDATE admins SET is_sudo = false WHERE role_id != 2"))
    else:
        conn.execute(sa.text("UPDATE admins SET is_sudo = 1 WHERE role_id = 2"))
        conn.execute(sa.text("UPDATE admins SET is_sudo = 0 WHERE role_id != 2"))
