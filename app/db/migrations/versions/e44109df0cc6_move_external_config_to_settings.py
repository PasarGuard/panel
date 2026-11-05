"""move EXTERNAL_CONFIG to the subscription external links setting

Revision ID: e44109df0cc6
Revises: d5e1f3a7b9c2
Create Date: 2026-11-05 00:00:00.000000

Copies the share links of the removed EXTERNAL_CONFIG env var (environment first, then ./.env like the env settings
read it) into subscription.external_links, after the links already there and without duplicates. Nothing is written
when it is unset or empty. Downgrade takes the links of EXTERNAL_CONFIG back out, since the older code reads the env
var again.
"""

import json
import logging
import os

import sqlalchemy as sa
from alembic import op

revision = "e44109df0cc6"
down_revision = "d5e1f3a7b9c2"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

ENV_NAME = "EXTERNAL_CONFIG"
KEY = "external_links"


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


def read_env_links(environ=None, dotenv: dict[str, str] | None = None) -> list[str]:
    """Share links of EXTERNAL_CONFIG, split on whitespace. The name matches in any case, like pydantic-settings."""
    environ = {key.upper(): value for key, value in (os.environ if environ is None else environ).items()}
    dotenv = {key.upper(): value for key, value in (_read_dotenv() if dotenv is None else dotenv).items()}
    raw = environ[ENV_NAME] if ENV_NAME in environ else dotenv.get(ENV_NAME, "")
    return raw.split()


def _stored_links(subscription: dict) -> list[str]:
    links = subscription.get(KEY)
    return [link for link in links if isinstance(link, str)] if isinstance(links, list) else []


def add_links(subscription: dict, links: list[str]) -> dict:
    """A copy of the subscription section with the links appended to external_links, skipping ones already there."""
    subscription = dict(subscription)
    stored = _stored_links(subscription)
    added = [link for link in dict.fromkeys(links) if link not in stored]
    if added:
        subscription[KEY] = stored + added
        logger.info(f"Moved {len(added)} {ENV_NAME} link(s) to panel setting subscription.{KEY}")
    return subscription


def remove_links(subscription: dict, links: list[str]) -> dict:
    """A copy of the subscription section without the links in external_links, the key dropped once it is empty."""
    subscription = dict(subscription)
    if KEY not in subscription:
        return subscription
    removed = set(links)
    kept = [link for link in _stored_links(subscription) if link not in removed]
    if kept:
        subscription[KEY] = kept
    else:
        subscription.pop(KEY)
    return subscription


def _settings_table():
    return sa.table("settings", sa.column("id", sa.Integer), sa.column("subscription", sa.JSON))


def _load(value):
    if isinstance(value, (str, bytes)):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def _rewrite(transform) -> None:
    bind = op.get_bind()
    table = _settings_table()
    rows = bind.execute(sa.select(table)).mappings().all()
    for row in rows:
        subscription = _load(row["subscription"])
        updated = transform(subscription)
        if updated != subscription:
            bind.execute(table.update().where(table.c.id == row["id"]).values(subscription=updated))


def upgrade() -> None:
    links = read_env_links()
    if not links:
        return
    _rewrite(lambda subscription: add_links(subscription, links))


def downgrade() -> None:
    links = read_env_links()
    if not links:
        return
    _rewrite(lambda subscription: remove_links(subscription, links))
