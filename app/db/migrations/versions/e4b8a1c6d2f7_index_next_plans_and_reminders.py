"""index next_plans.user_id and the notification reminder lookup

Revision ID: e4b8a1c6d2f7
Revises: f3a91b62d408
Create Date: 2026-11-15 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import context, op

revision = "e4b8a1c6d2f7"
down_revision = "f3a91b62d408"
branch_labels = None
depends_on = None

# PostgreSQL and SQLite do not index foreign key columns on their own, so the reminder checks and the
# ON DELETE CASCADE from users read these tables in full. MySQL/MariaDB already have an index under each FK.
_INDEXES = (
    ("ix_next_plans_user_id", "next_plans", ["user_id"], "fk_next_plans_user_id_users"),
    (
        "ix_notification_reminders_user_id_type_threshold",
        "notification_reminders",
        ["user_id", "type", "threshold"],
        "fk_notification_reminders_user_id_users",
    ),
)


def upgrade() -> None:
    for name, table_name, columns, _ in _INDEXES:
        if not _index_exists(table_name, name):
            op.create_index(name, table_name, columns, unique=False)
        _analyze(table_name)


def downgrade() -> None:
    for name, table_name, _, default_fk_name in reversed(_INDEXES):
        index_exists = _index_exists(table_name, name, default=True)
        if not _is_mysql():
            if index_exists:
                op.drop_index(name, table_name=table_name)
            continue
        # MySQL drops its own FK index once ours covers user_id and refuses to drop the last index a FK needs.
        # Re-adding the FK makes it build its own index again. Every statement commits on its own there, so each
        # step looks at what is left: a downgrade that stopped halfway is finished by running it again.
        fk_name = _fk_name(table_name, default_fk_name)
        if fk_name and not index_exists:
            continue
        if fk_name:
            op.drop_constraint(fk_name, table_name, type_="foreignkey")
        if index_exists:
            op.drop_index(name, table_name=table_name)
        op.create_foreign_key(fk_name or default_fk_name, table_name, "users", ["user_id"], ["id"], ondelete="CASCADE")


def _is_mysql() -> bool:
    return op.get_context().dialect.name in ("mysql", "mariadb")


def _index_exists(table_name: str, name: str, default: bool = False) -> bool:
    if context.is_offline_mode():
        return default
    return any(index["name"] == name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _fk_name(table_name: str, default: str) -> str | None:
    """Name of the user_id foreign key, or None when the table has none (offline: the expected name)."""
    if context.is_offline_mode():
        return default
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table_name):
        if fk["constrained_columns"] == ["user_id"] and fk["referred_table"] == "users" and fk["name"]:
            return fk["name"]
    return None


def _analyze(table_name: str) -> None:
    if _is_mysql():
        op.execute(sa.text(f"ANALYZE TABLE {table_name}"))
        return

    op.execute(sa.text(f"ANALYZE {table_name}"))
