"""add admin_id to user_templates

Revision ID: 4b348c37504f
Revises: 6a9fff8290b9
Create Date: 2026-08-14 00:00:00.000000

"""

import json

import sqlalchemy as sa
from alembic import op

import app.db.compiles_types

# revision identifiers, used by Alembic.
revision = "4b348c37504f"
down_revision = "6a9fff8290b9"
branch_labels = None
depends_on = None


TEMPLATES_SCOPE_ALL = {
    "create": True,
    "read": {"scope": 2},
    "read_simple": {"scope": 2},
    "update": {"scope": 2},
    "delete": {"scope": 2},
}
TEMPLATES_SCOPE_OWN = {
    "create": True,
    "read": {"scope": 1},
    "read_simple": {"scope": 1},
    "update": {"scope": 1},
    "delete": {"scope": 1},
}
TEMPLATES_LEGACY_UNRESTRICTED = {
    "create": True,
    "read": True,
    "read_simple": True,
    "update": True,
    "delete": True,
}
TEMPLATES_LEGACY_OPERATOR = {
    "create": False,
    "read": True,
    "read_simple": True,
    "update": False,
    "delete": False,
}

# Seed roles (by name) whose `templates` permissions get rewritten to use the new
# admin_id-based scope. Any custom/renamed roles are left untouched.
_UPGRADE_TEMPLATES_BY_ROLE_NAME = {
    "owner": TEMPLATES_SCOPE_ALL,
    "administrator": TEMPLATES_SCOPE_ALL,
    "operator": TEMPLATES_SCOPE_OWN,
}
_DOWNGRADE_TEMPLATES_BY_ROLE_NAME = {
    "owner": TEMPLATES_LEGACY_UNRESTRICTED,
    "administrator": TEMPLATES_LEGACY_UNRESTRICTED,
    "operator": TEMPLATES_LEGACY_OPERATOR,
}


def _normalize_permissions(value):
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    if isinstance(value, dict):
        return value
    return {}


def _admin_roles_table():
    return sa.table(
        "admin_roles",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("permissions", sa.JSON),
    )


def _update_role_templates_permissions(conn, templates_by_role_name: dict) -> None:
    admin_roles = _admin_roles_table()
    rows = conn.execute(sa.select(admin_roles.c.id, admin_roles.c.name, admin_roles.c.permissions)).fetchall()
    for role_id, role_name, role_permissions in rows:
        new_templates = templates_by_role_name.get(role_name)
        if new_templates is None:
            continue
        permissions = _normalize_permissions(role_permissions)
        permissions["templates"] = new_templates
        conn.execute(admin_roles.update().where(admin_roles.c.id == role_id).values(permissions=permissions))


def _set_operator_api_key_create(conn, create_value: bool | None) -> None:
    """Grant (or revoke) `create` on api_keys for the `operator` seed role only."""
    admin_roles = _admin_roles_table()
    rows = conn.execute(sa.select(admin_roles.c.id, admin_roles.c.name, admin_roles.c.permissions)).fetchall()
    for role_id, role_name, role_permissions in rows:
        if role_name != "operator":
            continue
        permissions = _normalize_permissions(role_permissions)
        api_keys_perms = dict(permissions.get("api_keys") or {})
        if create_value is None:
            api_keys_perms.pop("create", None)
        else:
            api_keys_perms["create"] = create_value
        permissions["api_keys"] = api_keys_perms
        conn.execute(admin_roles.update().where(admin_roles.c.id == role_id).values(permissions=permissions))


def upgrade() -> None:
    # Match the actual type of admins.id (may be INT or BIGINT depending on
    # whether the bigint migration has run on this database).
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    admins_id_type = inspector.get_columns("admins")[0]["type"]
    is_bigint = "BIGINT" in str(admins_id_type).upper()
    col_type = app.db.compiles_types.SqliteCompatibleBigInteger() if is_bigint else sa.Integer()

    with op.batch_alter_table("user_templates", schema=None) as batch_op:
        batch_op.add_column(sa.Column("admin_id", col_type, nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_user_templates_admin_id_admins"), "admins", ["admin_id"], ["id"]
        )
        batch_op.create_index(batch_op.f("ix_user_templates_admin_id"), ["admin_id"], unique=False)

    _update_role_templates_permissions(op.get_bind(), _UPGRADE_TEMPLATES_BY_ROLE_NAME)
    _set_operator_api_key_create(op.get_bind(), True)


def downgrade() -> None:
    _update_role_templates_permissions(op.get_bind(), _DOWNGRADE_TEMPLATES_BY_ROLE_NAME)
    _set_operator_api_key_create(op.get_bind(), None)

    with op.batch_alter_table("user_templates", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_templates_admin_id"))
        batch_op.drop_constraint(batch_op.f("fk_user_templates_admin_id_admins"), type_="foreignkey")
        batch_op.drop_column("admin_id")
