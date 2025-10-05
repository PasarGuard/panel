"""migrate to sqlalchemy v2

Revision ID: 1f6e978be88e
Revises: 0d22271ee06e
Create Date: 2025-03-22 22:08:45.392485

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql, postgresql
from app.db.models import CaseSensitiveString


# revision identifiers, used by Alembic.
revision = "1f6e978be88e"
down_revision = "0d22271ee06e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    dialect = connection.dialect.name
    # Alter admin_usage_logs table
    with op.batch_alter_table("admin_usage_logs") as batch_op:
        batch_op.alter_column("admin_id", existing_type=sa.INTEGER(), nullable=False)
        batch_op.alter_column("reset_at", existing_type=sa.DATETIME(), nullable=False)

    # Alter admins table
    with op.batch_alter_table("admins") as batch_op:
        batch_op.alter_column("username", existing_type=sa.VARCHAR(length=34), nullable=False)
        batch_op.alter_column("hashed_password", existing_type=sa.VARCHAR(length=128), nullable=False)
        batch_op.alter_column("created_at", existing_type=sa.DATETIME(), nullable=False)
        batch_op.alter_column(
            "is_sudo", existing_type=sa.BOOLEAN(), nullable=False, existing_server_default=sa.text("0")
        )

    # Alter groups table
    with op.batch_alter_table("groups") as batch_op:
        batch_op.alter_column("name", existing_type=sa.VARCHAR(length=64), nullable=False)

    # Alter node_usages table
    with op.batch_alter_table("node_usages") as batch_op:
        batch_op.alter_column("uplink", existing_type=sa.BIGINT(), nullable=False)
        batch_op.alter_column("downlink", existing_type=sa.BIGINT(), nullable=False)

    # Alter node_user_usages table
    with op.batch_alter_table("node_user_usages") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.INTEGER(), nullable=False)
        batch_op.alter_column("used_traffic", existing_type=sa.BIGINT(), nullable=False)

    # Alter nodes table
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.alter_column("name", existing_type=sa.VARCHAR(length=256), nullable=False)
        batch_op.alter_column("created_at", existing_type=sa.DATETIME(), nullable=False)
        batch_op.alter_column("uplink", existing_type=sa.BIGINT(), nullable=False)
        batch_op.alter_column("downlink", existing_type=sa.BIGINT(), nullable=False)

    # Alter notification_reminders table
    with op.batch_alter_table("notification_reminders") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.INTEGER(), nullable=False)
        batch_op.alter_column("created_at", existing_type=sa.DATETIME(), nullable=False)

    # Alter system table
    with op.batch_alter_table("system") as batch_op:
        batch_op.alter_column("uplink", existing_type=sa.BIGINT(), nullable=False)
        batch_op.alter_column("downlink", existing_type=sa.BIGINT(), nullable=False)

    # Alter user_templates table
    with op.batch_alter_table("user_templates") as batch_op:
        batch_op.alter_column("data_limit", existing_type=sa.BIGINT(), nullable=False)
        batch_op.alter_column("expire_duration", existing_type=sa.BIGINT(), nullable=False)

    # Alter user_usage_logs table
    with op.batch_alter_table("user_usage_logs") as batch_op:
        batch_op.alter_column("reset_at", existing_type=sa.DATETIME(), nullable=False)

    # Alter users table
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("username", existing_type=sa.VARCHAR(length=34), type_=CaseSensitiveString(length=34), nullable=False)
        batch_op.alter_column("used_traffic", existing_type=sa.BIGINT(), nullable=False)
        if dialect == "sqlite":
            batch_op.alter_column(
                "created_at",
                existing_type=sa.DATETIME(),
                nullable=False,
                existing_server_default=sa.text("(CURRENT_TIMESTAMP)"),
            )
        elif dialect == "mysql":
            batch_op.alter_column(
                "created_at", existing_type=mysql.DATETIME(), nullable=False, existing_server_default=sa.text("(now())")
            )
        elif dialect == "postgresql":
            batch_op.alter_column(
                "created_at",
                existing_type=postgresql.TIMESTAMP(),
                nullable=False,
                existing_server_default=sa.text("CURRENT_TIMESTAMP"),
            )

    if dialect == "mysql":
        op.alter_column(
            "hosts",
            "alpn",
            existing_type=mysql.ENUM("h3", "h3,h2", "h3,h2,http/1.1", "none", "h2", "http/1.1", "h2,http/1.1"),
            type_=sa.Enum(
                "none", "h3", "h2", "http/1.1", "h3,h2,http/1.1", "h3,h2", "h2,http/1.1", name="proxyhostalpn"
            ),
            existing_nullable=False,
        )
        op.alter_column(
            "users",
            "status",
            existing_type=mysql.ENUM("on_hold", "active", "limited", "expired", "disabled"),
            type_=sa.Enum("active", "disabled", "limited", "expired", "on_hold", name="userstatus"),
            existing_nullable=False,
        )

    if dialect == "postgresql":
        op.alter_column(
            "users",
            "proxy_settings",
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            type_=sa.JSON(none_as_null=True),
            existing_nullable=False,
            existing_server_default=sa.text("'{}'::jsonb"),
        )

    # ### end Alembic commands ###


def downgrade() -> None:
    connection = op.get_bind()
    dialect = connection.dialect.name

    if dialect == "postgresql":
        op.alter_column(
            "users",
            "proxy_settings",
            existing_type=sa.JSON(none_as_null=True),
            type_=postgresql.JSONB(astext_type=sa.Text()),
            existing_nullable=False,
            existing_server_default=sa.text("'{}'::jsonb"),
            postgresql_using="proxy_settings::jsonb",
        )

    if dialect == "mysql":
        op.alter_column(
            "users",
            "status",
            existing_type=sa.Enum("active", "disabled", "limited", "expired", "on_hold", name="userstatus"),
            type_=mysql.ENUM("on_hold", "active", "limited", "expired", "disabled"),
            existing_nullable=False,
        )
        op.alter_column(
            "hosts",
            "alpn",
            existing_type=sa.Enum(
                "none", "h3", "h2", "http/1.1", "h3,h2,http/1.1", "h3,h2", "h2,http/1.1", name="proxyhostalpn"
            ),
            type_=mysql.ENUM("h3", "h3,h2", "h3,h2,http/1.1", "none", "h2", "http/1.1", "h2,http/1.1"),
            existing_nullable=False,
        )

    # Alter users table
    with op.batch_alter_table("users") as batch_op:
        if dialect == "sqlite":
            batch_op.alter_column(
                "created_at",
                existing_type=sa.DATETIME(),
                nullable=True,
                existing_server_default=sa.text("(CURRENT_TIMESTAMP)"),
            )

        elif dialect == "mysql":
            batch_op.alter_column(
                "created_at", existing_type=mysql.DATETIME(), nullable=True, existing_server_default=sa.text("(now())")
            )

        elif dialect == "postgresql":
            batch_op.alter_column(
                "created_at",
                existing_type=postgresql.TIMESTAMP(),
                nullable=True,
                existing_server_default=sa.text("CURRENT_TIMESTAMP"),
            )

        batch_op.alter_column("used_traffic", existing_type=sa.BIGINT(), nullable=True)
        batch_op.alter_column("username", existing_type=sa.VARCHAR(length=34), type_=CaseSensitiveString(length=34), nullable=True)

    # Alter user_usage_logs table
    with op.batch_alter_table("user_usage_logs") as batch_op:
        batch_op.alter_column("reset_at", existing_type=sa.DATETIME(), nullable=True)

    # Alter user_templates table
    with op.batch_alter_table("user_templates") as batch_op:
        batch_op.alter_column("expire_duration", existing_type=sa.BIGINT(), nullable=True)
        batch_op.alter_column("data_limit", existing_type=sa.BIGINT(), nullable=True)

    # Alter system table
    with op.batch_alter_table("system") as batch_op:
        batch_op.alter_column("downlink", existing_type=sa.BIGINT(), nullable=True)
        batch_op.alter_column("uplink", existing_type=sa.BIGINT(), nullable=True)

    # Alter notification_reminders table
    with op.batch_alter_table("notification_reminders") as batch_op:
        batch_op.alter_column("created_at", existing_type=sa.DATETIME(), nullable=True)
        batch_op.alter_column("user_id", existing_type=sa.INTEGER(), nullable=True)

    # Alter nodes table
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.alter_column("downlink", existing_type=sa.BIGINT(), nullable=True)
        batch_op.alter_column("uplink", existing_type=sa.BIGINT(), nullable=True)
        batch_op.alter_column("created_at", existing_type=sa.DATETIME(), nullable=True)
        batch_op.alter_column("name", existing_type=sa.VARCHAR(length=256), nullable=True)

    # Alter node_user_usages table
    with op.batch_alter_table("node_user_usages") as batch_op:
        batch_op.alter_column("used_traffic", existing_type=sa.BIGINT(), nullable=True)
        batch_op.alter_column("user_id", existing_type=sa.INTEGER(), nullable=True)

    # Alter node_usages table
    with op.batch_alter_table("node_usages") as batch_op:
        batch_op.alter_column("downlink", existing_type=sa.BIGINT(), nullable=True)
        batch_op.alter_column("uplink", existing_type=sa.BIGINT(), nullable=True)

    # Alter groups table
    with op.batch_alter_table("groups") as batch_op:
        batch_op.alter_column("name", existing_type=sa.VARCHAR(length=64), nullable=True)

    # Alter admins table
    with op.batch_alter_table("admins") as batch_op:
        batch_op.alter_column(
            "is_sudo", existing_type=sa.BOOLEAN(), nullable=True, existing_server_default=sa.text("0")
        )
        batch_op.alter_column("created_at", existing_type=sa.DATETIME(), nullable=True)
        batch_op.alter_column("hashed_password", existing_type=sa.VARCHAR(length=128), nullable=True)
        batch_op.alter_column("username", existing_type=sa.VARCHAR(length=34), nullable=True)

    # Alter admin_usage_logs table
    with op.batch_alter_table("admin_usage_logs") as batch_op:
        batch_op.alter_column("reset_at", existing_type=sa.DATETIME(), nullable=True)
        batch_op.alter_column("admin_id", existing_type=sa.INTEGER(), nullable=True)
