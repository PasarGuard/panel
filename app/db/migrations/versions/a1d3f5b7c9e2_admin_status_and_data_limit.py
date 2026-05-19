"""admin status enum, data_limit, last_status_change, role limit columns

Revision ID: a1d3f5b7c9e2
Revises: b1e4f9a2c3d5
Create Date: 2026-05-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1d3f5b7c9e2'
down_revision = 'b1e4f9a2c3d5'
branch_labels = None
depends_on = None

_ADMIN_STATUS_ENUM = sa.Enum('active', 'disabled', 'limited', name='adminstatus')


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    # Create the enum type for PostgreSQL
    if dialect == "postgresql":
        _ADMIN_STATUS_ENUM.create(conn, checkfirst=True)

    # --- admins table ---
    with op.batch_alter_table('admins', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('status', sa.Enum('active', 'disabled', 'limited', name='adminstatus'),
                      nullable=True, server_default='active')
        )
        batch_op.add_column(sa.Column('data_limit', sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column('last_status_change', sa.DateTime(timezone=True), nullable=True))

    # Backfill status from is_disabled
    if dialect == "postgresql":
        conn.execute(sa.text(
            "UPDATE admins SET status = CASE "
            "WHEN is_disabled = true THEN 'disabled'::adminstatus "
            "ELSE 'active'::adminstatus END"
        ))
    else:
        conn.execute(sa.text(
            "UPDATE admins SET status = CASE WHEN is_disabled = 1 THEN 'disabled' ELSE 'active' END"
        ))

    # Make status NOT NULL
    with op.batch_alter_table('admins', schema=None) as batch_op:
        batch_op.alter_column('status', nullable=False,
                              existing_type=sa.Enum('active', 'disabled', 'limited', name='adminstatus'))

    # Drop is_disabled column
    with op.batch_alter_table('admins', schema=None) as batch_op:
        batch_op.drop_column('is_disabled')

    # --- admin_roles table: add dedicated boolean columns ---
    with op.batch_alter_table('admin_roles', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('disabled_when_limited', sa.Boolean(), nullable=False, server_default='0')
        )
        batch_op.add_column(
            sa.Column('disable_users_when_limited', sa.Boolean(), nullable=False, server_default='1')
        )


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    # Drop role limit columns
    with op.batch_alter_table('admin_roles', schema=None) as batch_op:
        batch_op.drop_column('disable_users_when_limited')
        batch_op.drop_column('disabled_when_limited')

    # Restore is_disabled from status
    with op.batch_alter_table('admins', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_disabled', sa.Boolean(), nullable=True, server_default='0')
        )

    if dialect == "postgresql":
        conn.execute(sa.text(
            "UPDATE admins SET is_disabled = (status = 'disabled'::adminstatus)"
        ))
    else:
        conn.execute(sa.text(
            "UPDATE admins SET is_disabled = CASE WHEN status = 'disabled' THEN 1 ELSE 0 END"
        ))

    with op.batch_alter_table('admins', schema=None) as batch_op:
        batch_op.alter_column('is_disabled', nullable=False, existing_type=sa.Boolean())
        batch_op.drop_column('status')
        batch_op.drop_column('data_limit')
        batch_op.drop_column('last_status_change')

    if dialect == "postgresql":
        _ADMIN_STATUS_ENUM.drop(conn, checkfirst=True)
