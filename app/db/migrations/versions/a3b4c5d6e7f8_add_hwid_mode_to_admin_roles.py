"""add hwid mode to admin roles

Revision ID: a3b4c5d6e7f8
Revises: f9c69a49f544
Create Date: 2026-06-13 00:00:00.000000

"""

import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a3b4c5d6e7f8"
down_revision = "f9c69a49f544"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        _upgrade_sqlite()
    elif dialect == "postgresql":
        _upgrade_postgresql()
    else:
        _upgrade_mysql()


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        _downgrade_sqlite()
    elif dialect == "postgresql":
        _downgrade_postgresql()
    else:
        _downgrade_mysql()


def _upgrade_sqlite():
    """SQLite: read all rows, update JSON in Python, write back."""
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, hwid FROM admin_roles")).fetchall()
    for row in rows:
        hwid_data = json.loads(row[1]) if isinstance(row[1], str) else (row[1] or {})
        if "mode" not in hwid_data:
            hwid_data["mode"] = "use_global"
        conn.execute(
            sa.text("UPDATE admin_roles SET hwid = :hwid WHERE id = :id"),
            {"hwid": json.dumps(hwid_data), "id": row[0]},
        )


def _upgrade_postgresql():
    """PostgreSQL: use jsonb_set to safely add mode field."""
    op.execute(
        sa.text(
            "UPDATE admin_roles "
            "SET hwid = jsonb_set("
            "  COALESCE(hwid::jsonb, '{}'::jsonb), "
            "  '{mode}', "
            "  '\"use_global\"'::jsonb"
            ") "
            "WHERE (hwid->>'mode') IS NULL"
        )
    )


def _upgrade_mysql():
    """MySQL: use JSON_SET."""
    op.execute(
        sa.text(
            'UPDATE admin_roles SET hwid = JSON_SET(hwid, "$.mode", "use_global") '
            "WHERE JSON_EXTRACT(hwid, \"$.mode\") IS NULL"
        )
    )


def _downgrade_sqlite():
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, hwid FROM admin_roles")).fetchall()
    for row in rows:
        hwid_data = json.loads(row[1]) if isinstance(row[1], str) else (row[1] or {})
        hwid_data.pop("mode", None)
        conn.execute(
            sa.text("UPDATE admin_roles SET hwid = :hwid WHERE id = :id"),
            {"hwid": json.dumps(hwid_data), "id": row[0]},
        )


def _downgrade_postgresql():
    op.execute(
        sa.text(
            "UPDATE admin_roles "
            "SET hwid = COALESCE(hwid::jsonb, '{}'::jsonb) - 'mode' "
            "WHERE (hwid->>'mode') IS NOT NULL"
        )
    )


def _downgrade_mysql():
    op.execute(
        sa.text('UPDATE admin_roles SET hwid = JSON_REMOVE(hwid, "$.mode")')
    )
