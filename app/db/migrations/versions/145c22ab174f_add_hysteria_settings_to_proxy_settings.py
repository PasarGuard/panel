"""add hysteria settings to proxy settings

Revision ID: 145c22ab174f
Revises: e8c6a4f1d2b7
Create Date: 2026-03-27 20:53:14.317956

"""
import json
import sqlalchemy as sa
from alembic import op
from uuid import uuid4

# revision identifiers, used by Alembic.
revision = '145c22ab174f'
down_revision = 'e8c6a4f1d2b7'
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

        hysteria = proxy_settings.get('hysteria', {})
        if not isinstance(hysteria, dict):
            hysteria = {}

        if 'auth' not in hysteria:
            hysteria['auth'] = str(uuid4())
            proxy_settings['hysteria'] = hysteria
            updates.append({'_id': user_id, 'proxy_settings': json.dumps(proxy_settings)})

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
        if proxy_settings and 'hysteria' in proxy_settings:
            proxy_settings.pop('hysteria')
            updates.append({'_id': user_id, 'proxy_settings': json.dumps(proxy_settings)})

    if updates:
        bind.execute(
            users_table.update().where(users_table.c.id == sa.bindparam('_id')),
            updates,
        )
