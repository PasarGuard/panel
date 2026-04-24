"""normalize mysql metadata

Revision ID: b7d9e1a2c3f4
Revises: a1b2c3d4e5f6
Create Date: 2026-04-24 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = "b7d9e1a2c3f4"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


FINGERPRINT_TYPE = mysql.ENUM(
    "none",
    "chrome",
    "firefox",
    "safari",
    "ios",
    "android",
    "edge",
    "360",
    "qq",
    "random",
    "randomized",
    "randomizednoalpn",
    "unsafe",
)


def _is_mysql_family() -> bool:
    return op.get_bind().dialect.name in {"mysql", "mariadb"}


def _drop_nodes_core_config_fks() -> None:
    inspector = inspect(op.get_bind())
    for fk in inspector.get_foreign_keys("nodes"):
        if fk.get("constrained_columns") == ["core_config_id"] and fk.get("name"):
            op.drop_constraint(fk["name"], "nodes", type_="foreignkey")


def upgrade() -> None:
    if not _is_mysql_family():
        return

    op.execute(sa.text("UPDATE admins SET used_traffic = 0 WHERE used_traffic IS NULL"))
    op.alter_column(
        "admins",
        "used_traffic",
        existing_type=sa.BigInteger(),
        nullable=False,
        server_default=sa.text("0"),
    )

    op.execute(sa.text("UPDATE hosts SET fingerprint = 'none' WHERE fingerprint IS NULL"))
    op.alter_column(
        "hosts",
        "fingerprint",
        existing_type=FINGERPRINT_TYPE,
        nullable=False,
        existing_server_default=sa.text("'none'"),
    )

    _drop_nodes_core_config_fks()
    op.create_foreign_key(
        "fk_nodes_core_config_id_core_configs",
        "nodes",
        "core_configs",
        ["core_config_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    if not _is_mysql_family():
        return

    _drop_nodes_core_config_fks()
    op.create_foreign_key(
        "nodes_ibfk_1",
        "nodes",
        "core_configs",
        ["core_config_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column(
        "hosts",
        "fingerprint",
        existing_type=FINGERPRINT_TYPE,
        nullable=True,
        existing_server_default=sa.text("'none'"),
    )
    op.alter_column(
        "admins",
        "used_traffic",
        existing_type=sa.BigInteger(),
        nullable=True,
        server_default=sa.text("0"),
    )
