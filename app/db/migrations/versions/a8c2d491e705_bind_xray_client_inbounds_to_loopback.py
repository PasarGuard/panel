"""Bind generated Xray client proxy inbounds to loopback.

Revision ID: a8c2d491e705
Revises: fb32155473c1
Create Date: 2026-08-09
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "a8c2d491e705"
down_revision = "fb32155473c1"
branch_labels = None
depends_on = None


client_templates = sa.table(
    "client_templates",
    sa.column("id", sa.Integer()),
    sa.column("template_type", sa.String()),
    sa.column("content", sa.Text()),
    sa.column("is_system", sa.Boolean()),
)

EXPOSED_LISTENER = re.compile(r'("listen"\s*:\s*)"0\.0\.0\.0"')
INBOUNDS_ARRAY = re.compile(r'"inbounds"\s*:\s*\[')


def _json_array_end(content: str, start: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(content)):
        character = content[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _bind_client_listeners_to_loopback(content: str) -> str:
    """Rewrite only exposed Xray client listener values, preserving the template."""
    match = INBOUNDS_ARRAY.search(content)
    if not match:
        return content
    start = match.end() - 1
    end = _json_array_end(content, start)
    if end is None:
        return content
    inbounds = EXPOSED_LISTENER.sub(r'\1"127.0.0.1"', content[start:end])
    return content[:start] + inbounds + content[end:]


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(client_templates.c.id, client_templates.c.content).where(
            client_templates.c.template_type == "xray_subscription",
            client_templates.c.is_system.is_(True),
        )
    ).mappings()
    for row in rows:
        content = row["content"]
        updated_content = _bind_client_listeners_to_loopback(content)
        if updated_content == content:
            continue
        connection.execute(
            client_templates.update().where(client_templates.c.id == row["id"]).values(content=updated_content)
        )


def downgrade() -> None:
    # Do not reintroduce an unauthenticated network listener on downgrade.
    pass
