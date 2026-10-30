"""add use_jinja to client_templates and tag_prefix to hosts

Revision ID: 33ceb5c0a3a2
Revises: c8d2e4f6a1b3
Create Date: 2026-10-20 17:25:25.487373

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '33ceb5c0a3a2'
down_revision = 'c8d2e4f6a1b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("client_templates", schema=None) as batch_op:
        batch_op.add_column(sa.Column("use_jinja", sa.Boolean(), nullable=False, server_default=sa.false()))

    # Clash templates always render as Jinja2 (they need `conf`, built once the proxies exist); existing rows
    # predate this column and would otherwise come back as "plain" and never render at all.
    client_templates = sa.table("client_templates", sa.column("template_type", sa.String), sa.column("use_jinja", sa.Boolean))
    op.execute(client_templates.update().where(client_templates.c.template_type == "clash_subscription").values(use_jinja=True))

    with op.batch_alter_table("hosts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tag_prefix", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("hosts", schema=None) as batch_op:
        batch_op.drop_column("tag_prefix")

    with op.batch_alter_table("client_templates", schema=None) as batch_op:
        batch_op.drop_column("use_jinja")
