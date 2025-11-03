"""separate notifications channels

Revision ID: 5021dbccc95f
Revises: 5943013d0e49
Create Date: 2025-11-04 00:57:24.063123

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import json


# revision identifiers, used by Alembic.
revision = '5021dbccc95f'
down_revision = '5943013d0e49'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Transform notification_settings to use combined telegram_chat_id.
    Old: telegram_admin_id, telegram_channel_id, telegram_topic_id
    New: telegram_chat_id (channel_id OR admin_id), telegram_topic_id (only if channel_id was used)
    """
    connection = op.get_bind()

    # Get all settings rows
    result = connection.execute(text("SELECT id, notification_settings FROM settings"))
    rows = result.fetchall()

    for row in rows:
        settings_id = row[0]
        old_settings_json = row[1]

        if not old_settings_json:
            continue

        # Handle JSON parsing for different database types
        if isinstance(old_settings_json, str):
            old_settings = json.loads(old_settings_json)
        else:
            old_settings = old_settings_json

        # Extract old values once
        telegram_admin_id = old_settings.get("telegram_admin_id")
        telegram_channel_id = old_settings.get("telegram_channel_id")
        telegram_topic_id = old_settings.get("telegram_topic_id")

        # Combine telegram_channel_id and telegram_admin_id → telegram_chat_id
        # Priority: channel_id if exists, otherwise admin_id
        new_chat_id = telegram_channel_id if telegram_channel_id else telegram_admin_id

        # Keep topic_id ONLY if we're using channel_id (not admin_id)
        # If using admin_id directly, topic_id doesn't make sense
        new_topic_id = telegram_topic_id if telegram_channel_id else None

        # Create new settings structure
        new_settings = {
            "notify_telegram": old_settings.get("notify_telegram", False),
            "notify_discord": old_settings.get("notify_discord", False),
            "telegram_api_token": old_settings.get("telegram_api_token"),
            "telegram_chat_id": new_chat_id,
            "telegram_topic_id": new_topic_id,
            "discord_webhook_url": old_settings.get("discord_webhook_url"),
            "proxy_url": old_settings.get("proxy_url"),
            "max_retries": old_settings.get("max_retries", 3),
        }

        # Update the row with new structure
        connection.execute(
            text("UPDATE settings SET notification_settings = :new_settings WHERE id = :settings_id"),
            {"new_settings": json.dumps(new_settings), "settings_id": settings_id}
        )


def downgrade() -> None:
    """
    Rollback: Split telegram_chat_id back to admin_id and channel_id.
    Logic: If topic_id exists, it was a channel; otherwise it was admin_id.
    """
    connection = op.get_bind()

    # Get all settings rows
    result = connection.execute(text("SELECT id, notification_settings FROM settings"))
    rows = result.fetchall()

    for row in rows:
        settings_id = row[0]
        new_settings_json = row[1]

        if not new_settings_json:
            continue

        # Handle JSON parsing for different database types
        if isinstance(new_settings_json, str):
            new_settings = json.loads(new_settings_json)
        else:
            new_settings = new_settings_json

        # Extract new values
        telegram_chat_id = new_settings.get("telegram_chat_id")
        telegram_topic_id = new_settings.get("telegram_topic_id")

        # Split logic: If topic_id exists, chat_id was a channel; otherwise it was admin_id
        if telegram_topic_id:
            # Was using channel with topic
            telegram_channel_id = telegram_chat_id
            telegram_admin_id = None
        else:
            # Was using direct admin chat
            telegram_channel_id = None
            telegram_admin_id = telegram_chat_id

        # Create old settings structure
        old_settings = {
            "notify_telegram": new_settings.get("notify_telegram", False),
            "notify_discord": new_settings.get("notify_discord", False),
            "telegram_api_token": new_settings.get("telegram_api_token"),
            "telegram_admin_id": telegram_admin_id,
            "telegram_channel_id": telegram_channel_id,
            "telegram_topic_id": telegram_topic_id,
            "discord_webhook_url": new_settings.get("discord_webhook_url"),
            "proxy_url": new_settings.get("proxy_url"),
            "max_retries": new_settings.get("max_retries", 3),
        }

        # Update the row with old structure
        connection.execute(
            text("UPDATE settings SET notification_settings = :old_settings WHERE id = :settings_id"),
            {"old_settings": json.dumps(old_settings), "settings_id": settings_id}
        )
