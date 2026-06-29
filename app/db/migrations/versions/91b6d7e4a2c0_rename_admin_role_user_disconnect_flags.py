"""rename admin role user disconnect flags

Revision ID: 91b6d7e4a2c0
Revises: 7f2a9c4d1e8b
Create Date: 2026-06-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "91b6d7e4a2c0"
down_revision = "7f2a9c4d1e8b"
branch_labels = None
depends_on = None


def _bool_server_default():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        return sa.text("true")
    return sa.text("1")


def upgrade() -> None:
    bool_default = _bool_server_default()
    with op.batch_alter_table("admin_roles", schema=None) as batch_op:
        batch_op.alter_column(
            "disable_users_when_limited",
            new_column_name="disconnect_users_when_limited",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=bool_default,
        )
        batch_op.alter_column(
            "disable_users_when_disabled",
            new_column_name="disconnect_users_when_disabled",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=bool_default,
        )


def downgrade() -> None:
    bool_default = _bool_server_default()
    with op.batch_alter_table("admin_roles", schema=None) as batch_op:
        batch_op.alter_column(
            "disconnect_users_when_disabled",
            new_column_name="disable_users_when_disabled",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=bool_default,
        )
        batch_op.alter_column(
            "disconnect_users_when_limited",
            new_column_name="disable_users_when_limited",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=bool_default,
        )
