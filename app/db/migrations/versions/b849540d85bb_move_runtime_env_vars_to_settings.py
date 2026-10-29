"""move runtime env vars to panel settings

Revision ID: b849540d85bb
Revises: c8d2e4f6a1b3
Create Date: 2026-10-30 00:00:00.000000

Copies the values of env vars that became panel settings into the settings row, so existing installs keep their
behavior. Only vars that are set (environment first, then ./.env like the env settings read them) are written;
unset ones are left to the model defaults.
"""

import json
import logging
import os

import sqlalchemy as sa
from alembic import op

revision = "b849540d85bb"
down_revision = "c8d2e4f6a1b3"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_TRUE = {"1", "on", "t", "true", "y", "yes"}
_FALSE = {"0", "off", "f", "false", "n", "no"}


def _bool(value: str) -> bool:
    value = value.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"not a boolean: {value!r}")


def _not_bool(value: str) -> bool:
    return not _bool(value)


def _int(minimum: int | None = None):
    def parse(value: str) -> int:
        number = int(value.strip())
        if minimum is not None and number < minimum:
            raise ValueError(f"must be at least {minimum}")
        return number

    return parse


# env var -> (settings column, key path inside that column, parser)
ENV_SETTINGS = {
    "DISABLE_RECORDING_NODE_USAGE": ("general", ("usage", "record_node_usage"), _not_bool),
    "ENABLE_RECORDING_NODES_STATS": ("general", ("usage", "record_node_stats"), _bool),
    "RESET_USER_USAGE_CLEAN_CHART_DATA": ("general", ("usage", "reset_usage_clean_chart_data"), _bool),
    "NODE_HEALTH_FAIL_THRESHOLD": ("general", ("node_health", "fail_threshold"), _int(1)),
    "NODE_HEALTH_RECOVER_THRESHOLD": ("general", ("node_health", "recover_threshold"), _int(1)),
    "NODE_HEALTH_PROBE_TIMEOUT": ("general", ("node_health", "probe_timeout"), _int(1)),
    "NODE_HEALTH_MAX_BACKOFF": ("general", ("node_health", "max_backoff"), _int(0)),
    "STOP_NODES_ON_SHUTDOWN": ("general", ("stop_nodes_on_shutdown",), _bool),
    "JWT_ACCESS_TOKEN_EXPIRE_MINUTES": ("general", ("admin_token_expire_minutes",), _int()),
    "USER_SUBSCRIPTION_CLIENTS_LIMIT": ("subscription", ("clients_limit",), _int()),
    "DO_NOT_LOG_TELEGRAM_BOT": ("telegram", ("do_not_log_bot",), _bool),
}

# Keys this revision adds, removed again on downgrade.
ADDED_KEYS = {
    "general": ("usage", "node_health", "stop_nodes_on_shutdown", "admin_token_expire_minutes"),
    "subscription": ("clients_limit",),
    "telegram": ("do_not_log_bot",),
}

COLUMNS = ("general", "subscription", "telegram")


def _read_dotenv(path: str = ".env") -> dict[str, str]:
    if not os.path.isfile(path):
        return {}
    try:
        from dotenv import dotenv_values
    except ImportError:
        values = {}
        with open(path, encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip().removeprefix("export ").strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                values[key] = value
        return values
    return {key: value for key, value in dotenv_values(path).items() if value is not None}


def read_env_values(environ=None, dotenv: dict[str, str] | None = None) -> dict[str, str]:
    """Raw values of the moved env vars that are set. Names match in any case, like pydantic-settings."""
    environ = {key.upper(): value for key, value in (os.environ if environ is None else environ).items()}
    dotenv = {key.upper(): value for key, value in (_read_dotenv() if dotenv is None else dotenv).items()}
    values = {}
    for name in ENV_SETTINGS:
        if name in environ:
            values[name] = environ[name]
        elif name in dotenv:
            values[name] = dotenv[name]
    return values


def apply_env_values(sections: dict[str, dict], env_values: dict[str, str]) -> dict[str, dict]:
    """Writes the parsed env values into copies of the settings sections."""
    sections = {column: dict(sections.get(column) or {}) for column in COLUMNS}
    for name, raw in env_values.items():
        column, path, parse = ENV_SETTINGS[name]
        try:
            value = parse(raw)
        except ValueError as exc:
            logger.warning(f"Skipped {name}={raw!r}: {exc}")
            continue
        target = sections[column]
        for key in path[:-1]:
            nested = target.get(key)
            target[key] = nested = dict(nested) if isinstance(nested, dict) else {}
            target = nested
        target[path[-1]] = value
        logger.info(f"Moved {name}={raw!r} to panel setting {column}.{'.'.join(path)} = {value!r}")
    return sections


def remove_added_keys(sections: dict[str, dict]) -> dict[str, dict]:
    sections = {column: dict(sections.get(column) or {}) for column in COLUMNS}
    for column, keys in ADDED_KEYS.items():
        for key in keys:
            sections[column].pop(key, None)
    return sections


def _settings_table():
    return sa.table("settings", sa.column("id", sa.Integer), *(sa.column(column, sa.JSON) for column in COLUMNS))


def _load(value):
    if isinstance(value, (str, bytes)):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def _rewrite(transform) -> None:
    bind = op.get_bind()
    table = _settings_table()
    rows = bind.execute(sa.select(table)).mappings().all()
    for row in rows:
        sections = transform({column: _load(row[column]) for column in COLUMNS})
        bind.execute(table.update().where(table.c.id == row["id"]).values(**sections))


def upgrade() -> None:
    env_values = read_env_values()
    if not env_values:
        return
    _rewrite(lambda sections: apply_env_values(sections, env_values))


def downgrade() -> None:
    _rewrite(remove_added_keys)
