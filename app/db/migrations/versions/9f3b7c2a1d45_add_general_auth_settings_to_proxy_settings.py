"""add general auth settings to proxy settings

Revision ID: 9f3b7c2a1d45
Revises: 48a6bcb8bba1
Create Date: 2026-09-05 12:00:00.000000

"""
import json
import secrets

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '9f3b7c2a1d45'
down_revision = '48a6bcb8bba1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    users_table = sa.table(
        'users',
        sa.column('id', sa.Integer),
        sa.column('proxy_settings', sa.JSON),
    )

    users = bind.execute(sa.select(users_table.c.id, users_table.c.proxy_settings)).fetchall()

    updates = []
    for user_id, proxy_settings in users:
        if isinstance(proxy_settings, str):
            proxy_settings = json.loads(proxy_settings)
        if not proxy_settings:
            proxy_settings = {}
        if proxy_settings.get('general_auth'):
            continue

        proxy_settings['general_auth'] = {
            'username': secrets.token_urlsafe(24),
            'password': secrets.token_urlsafe(24),
        }
        updates.append({'_id': user_id, 'proxy_settings': proxy_settings})

    if updates:
        bind.execute(
            users_table.update().where(users_table.c.id == sa.bindparam('_id')),
            updates,
        )


def downgrade() -> None:
    bind = op.get_bind()

    users_table = sa.table(
        'users',
        sa.column('id', sa.Integer),
        sa.column('proxy_settings', sa.JSON),
    )

    users = bind.execute(sa.select(users_table.c.id, users_table.c.proxy_settings)).fetchall()

    updates = []
    for user_id, proxy_settings in users:
        if isinstance(proxy_settings, str):
            proxy_settings = json.loads(proxy_settings)
        if proxy_settings and 'general_auth' in proxy_settings:
            proxy_settings.pop('general_auth')
            updates.append({'_id': user_id, 'proxy_settings': proxy_settings})

    if updates:
        bind.execute(
            users_table.update().where(users_table.c.id == sa.bindparam('_id')),
            updates,
        )
