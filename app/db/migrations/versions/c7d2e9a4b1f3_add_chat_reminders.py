"""separate Telegram and Discord reminders from webhooks

Revision ID: c7d2e9a4b1f3
Revises: d5e1f3a7b9c2
Create Date: 2026-11-07 00:00:00.000000

"""

import json

import sqlalchemy as sa
from alembic import op

revision = "c7d2e9a4b1f3"
down_revision = "d5e1f3a7b9c2"
branch_labels = None
depends_on = None

_settings = sa.table("settings", sa.column("id", sa.Integer), sa.column("notification_enable", sa.JSON))


def _rewrite_notification_enable(change) -> None:
    bind = op.get_bind()
    update = (
        _settings.update()
        .where(_settings.c.id == sa.bindparam("_id"))
        .values(notification_enable=sa.bindparam("_value", type_=sa.JSON))
    )
    for row in bind.execute(sa.select(_settings.c.id, _settings.c.notification_enable)).fetchall():
        value = (
            json.loads(row.notification_enable) if isinstance(row.notification_enable, str) else row.notification_enable
        )
        if isinstance(value, dict):
            change(value)
            bind.execute(update, {"_id": row.id, "_value": value})


def upgrade() -> None:
    """Add a marker that keeps chat reminders apart from webhook ones, and turn chat reminders off.

    The two toggles used to gate webhook reminders, but nothing has read them since 3b0678c1 (2025-08-01) apart from
    an unreleased change that sent chat messages. Webhooks keep working from their own settings, so nobody loses a
    working setup. Existing reminder rows belong to webhooks.
    """
    with op.batch_alter_table("notification_reminders") as batch_op:
        batch_op.add_column(sa.Column("for_chat", sa.Boolean(), nullable=False, server_default=sa.false()))

    def turn_off(value: dict) -> None:
        value.update(
            days_left=False, days_left_thresholds=[], percentage_reached=False, percentage_reached_thresholds=[]
        )

    _rewrite_notification_enable(turn_off)


def downgrade() -> None:
    def drop_thresholds(value: dict) -> None:
        value.pop("days_left_thresholds", None)
        value.pop("percentage_reached_thresholds", None)

    _rewrite_notification_enable(drop_thresholds)

    reminders = sa.table("notification_reminders", sa.column("for_chat", sa.Boolean))
    op.get_bind().execute(reminders.delete().where(reminders.c.for_chat == sa.true()))
    with op.batch_alter_table("notification_reminders") as batch_op:
        batch_op.drop_column("for_chat")
