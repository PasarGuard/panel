"""add cleanup retention settings

Revision ID: f0420da90ff1
Revises: e5a7c3f9b214
Create Date: 2026-10-30 00:00:00.000000

Adds the cleanup settings section. Every retention period starts as "keep forever", so an upgrade deletes nothing.
USERS_AUTODELETE_DAYS and USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS move into it when they are set (environment
first, then ./.env, like the env settings read them).
"""

import logging
import os

import sqlalchemy as sa
from alembic import op

revision = "f0420da90ff1"
down_revision = "e5a7c3f9b214"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

MAX_RETENTION_DAYS = 36_500
_TRUE = {"1", "on", "t", "true", "y", "yes"}
_FALSE = {"0", "off", "f", "false", "n", "no"}


def _read_dotenv(path: str = ".env") -> dict[str, str]:
    if not os.path.isfile(path):
        return {}
    from dotenv import dotenv_values

    return {key: value for key, value in dotenv_values(path).items() if value is not None}


def read_env_values(environ=None, dotenv: dict[str, str] | None = None) -> dict[str, str]:
    """Raw values of the moved env vars that are set. Names match in any case, like pydantic-settings."""
    environ = {key.upper(): value for key, value in (os.environ if environ is None else environ).items()}
    dotenv = {key.upper(): value for key, value in (_read_dotenv() if dotenv is None else dotenv).items()}
    values = {}
    for name in ("USERS_AUTODELETE_DAYS", "USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS"):
        if name in environ:
            values[name] = environ[name]
        elif name in dotenv:
            values[name] = dotenv[name]
    return values


def build_cleanup(env_values: dict[str, str]) -> dict:
    """The cleanup section for an existing install. Unset or invalid values keep the defaults."""
    cleanup = {}
    if (raw := env_values.get("USERS_AUTODELETE_DAYS")) is not None:
        try:
            days = int(raw.strip())
        except ValueError:
            logger.warning(f"Skipped USERS_AUTODELETE_DAYS={raw!r}: not a whole number")
        else:
            # Negative values disabled auto delete, which is the new default
            if days >= 0:
                cleanup["expired_users_retention_days"] = min(days, MAX_RETENTION_DAYS)
                logger.info(
                    f"Moved USERS_AUTODELETE_DAYS={raw!r} to panel setting cleanup.expired_users_retention_days"
                )
    if (raw := env_values.get("USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS")) is not None:
        value = raw.strip().lower()
        if value in _TRUE | _FALSE:
            cleanup["include_limited_users"] = value in _TRUE
            logger.info(
                f"Moved USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS={raw!r} to panel setting cleanup.include_limited_users"
            )
        else:
            logger.warning(f"Skipped USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS={raw!r}: not a boolean")
    return cleanup


def upgrade() -> None:
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cleanup", sa.JSON(), nullable=True))

    settings_table = sa.table("settings", sa.column("cleanup", sa.JSON()))
    op.execute(settings_table.update().values(cleanup=build_cleanup(read_env_values())))

    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.alter_column("cleanup", existing_type=sa.JSON(), nullable=False)

    with op.batch_alter_table("node_stats", schema=None) as batch_op:
        batch_op.create_index("ix_node_stats_created_at", ["created_at"], unique=False)
        batch_op.create_index("ix_node_stats_node_id_created_at", ["node_id", "created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name in ("mysql", "mariadb"):
        # MySQL dropped the foreign key's own index when the (node_id, created_at) index could serve it;
        # it has to exist again before that index can go
        index_names = {index["name"] for index in sa.inspect(bind).get_indexes("node_stats")}
        if "fk_node_stats_node_id_nodes" not in index_names:
            op.create_index("fk_node_stats_node_id_nodes", "node_stats", ["node_id"])

    with op.batch_alter_table("node_stats", schema=None) as batch_op:
        batch_op.drop_index("ix_node_stats_node_id_created_at")
        batch_op.drop_index("ix_node_stats_created_at")

    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("cleanup")
