"""add hwid device limit

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-30 22:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    users_columns = {col["name"]: col for col in inspect(bind).get_columns("users")}
    users_id_type = users_columns.get("id", {}).get("type")
    users_id_type_repr = str(users_id_type).upper() if users_id_type is not None else ""
    users_id_is_unsigned = bool(getattr(users_id_type, "unsigned", False))
    if "BIGINT" in users_id_type_repr:
        if dialect_name == "mysql" and (users_id_is_unsigned or "UNSIGNED" in users_id_type_repr):
            user_id_column_type = mysql.BIGINT(unsigned=True)
        else:
            user_id_column_type = sa.BigInteger()
    else:
        user_id_column_type = sa.Integer()

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("hwid_device_limit", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("hwid_limit_disabled", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.create_check_constraint(
            "ck_users_hwid_device_limit_non_negative",
            "hwid_device_limit IS NULL OR hwid_device_limit >= 0",
        )

    op.create_table(
        "hwid_user_devices",
        sa.Column("id", user_id_column_type, nullable=False),
        sa.Column("user_id", user_id_column_type, nullable=False),
        sa.Column("hwid_hash", sa.String(length=128), nullable=False),
        sa.Column("device_os", sa.String(length=64), nullable=True),
        sa.Column("os_version", sa.String(length=64), nullable=True),
        sa.Column("device_model", sa.String(length=128), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("request_ip", sa.String(length=64), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "hwid_hash"),
    )
    if dialect_name == "mysql":
        # Ensure table collation/engine defaults don't interfere with FK creation.
        op.execute(sa.text("ALTER TABLE hwid_user_devices ENGINE=InnoDB"))
    op.create_index("ix_hwid_user_devices_user_id_last_seen_at", "hwid_user_devices", ["user_id", "last_seen_at"])
    op.create_index("ix_hwid_user_devices_hwid_hash", "hwid_user_devices", ["hwid_hash"])
    op.create_index("ix_hwid_user_devices_last_seen_at", "hwid_user_devices", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_hwid_user_devices_last_seen_at", table_name="hwid_user_devices")
    op.drop_index("ix_hwid_user_devices_hwid_hash", table_name="hwid_user_devices")
    op.drop_index("ix_hwid_user_devices_user_id_last_seen_at", table_name="hwid_user_devices")
    op.drop_table("hwid_user_devices")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_hwid_device_limit_non_negative", type_="check")
        batch_op.drop_column("hwid_limit_disabled")
        batch_op.drop_column("hwid_device_limit")

