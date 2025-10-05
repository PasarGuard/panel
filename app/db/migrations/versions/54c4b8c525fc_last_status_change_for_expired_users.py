"""last_status_change_for_expired_users

Revision ID: 54c4b8c525fc
Revises: 2313cdc30da3
Create Date: 2024-07-25 11:15:51.776880

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func, case, text
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '54c4b8c525fc'
down_revision = '2313cdc30da3'
branch_labels = None
depends_on = None

# Define the 'users' table
users_table = sa.Table(
    'users',
    sa.MetaData(),
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('status', sa.String),
    sa.Column('expire', sa.Integer),  # Assuming 'expire' is a UNIX timestamp
    sa.Column('last_status_change', sa.DateTime)
)


def upgrade() -> None:
    # Get database connection and dialect
    connection = op.get_bind()
    dialect = connection.dialect.name

    # Create the update statement based on dialect
    if dialect == 'postgresql':
        update_stmt = text("""
            UPDATE users 
            SET last_status_change = to_timestamp(expire)
            WHERE status = 'expired' AND expire IS NOT NULL
        """)
    elif dialect == 'mysql':
        update_stmt = text("""
            UPDATE users 
            SET last_status_change = FROM_UNIXTIME(expire)
            WHERE status = 'expired' AND expire IS NOT NULL
        """)
    else:  # sqlite
        update_stmt = text("""
            UPDATE users 
            SET last_status_change = datetime(expire, 'unixepoch')
            WHERE status = 'expired' AND expire IS NOT NULL
        """)

    connection.execute(update_stmt)


def downgrade() -> None:
    connection = op.get_bind()

    # Set last_status_change to the current timestamp for 'expired' users
    update_stmt = (
        sa.update(users_table)
        .where(
            sa.and_(
                users_table.c.status == 'expired',
                users_table.c.expire.isnot(None)
            )
        )
        .values(last_status_change=func.now())  # CURRENT_TIMESTAMP equivalent
    )

    # Execute the update statement
    connection.execute(update_stmt)
