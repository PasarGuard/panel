"""remove discord bot settings

Revision ID: 4b1b42d5a8c0
Revises: 2c6e9d34a1f0
Create Date: 2026-05-31 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4b1b42d5a8c0"
down_revision = "2c6e9d34a1f0"
branch_labels = None
depends_on = None


DEFAULT_DISCORD_SETTINGS = {"enable": False, "token": None, "proxy_url": None}


def upgrade() -> None:
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("discord")


def downgrade() -> None:
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("discord", sa.JSON(), nullable=True))

    settings_table = sa.table("settings", sa.column("discord", sa.JSON()))
    op.execute(settings_table.update().values(discord=DEFAULT_DISCORD_SETTINGS))

    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.alter_column("discord", existing_type=sa.JSON(), type_=sa.JSON(), nullable=False)
