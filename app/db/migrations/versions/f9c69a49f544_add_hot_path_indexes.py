"""add hot path indexes

Revision ID: f9c69a49f544
Revises: 91b6d7e4a2c0
Create Date: 2026-06-07 12:41:28.546462

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9c69a49f544'
down_revision = '91b6d7e4a2c0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    _create_index("idx_user_subscription_updates_user_id", "user_subscription_updates", ["user_id"])
    _create_index("idx_users_admin_online", "users", ["admin_id", "online_at"])
    _create_index("idx_users_admin_status", "users", ["admin_id", "status"])
    _create_index("idx_users_admin_created", "users", ["admin_id", "created_at"])
    _analyze_users()


def downgrade() -> None:
    _drop_index("idx_users_admin_created", "users")
    _drop_index("idx_users_admin_status", "users")
    _drop_index("idx_users_admin_online", "users")
    _drop_index("idx_user_subscription_updates_user_id", "user_subscription_updates")


def _create_index(name: str, table_name: str, columns: list) -> None:
    op.create_index(name, table_name, columns, unique=False)


def _drop_index(name: str, table_name: str) -> None:
    op.drop_index(name, table_name=table_name)


def _analyze_users() -> None:
    if op.get_bind().dialect.name == "mysql":
        op.execute(sa.text("ANALYZE TABLE users"))
        return

    op.execute(sa.text("ANALYZE users"))
