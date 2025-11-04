from app.models.admin import AdminContactInfo
from app.models.settings import NotificationSettings


def get_telegram_channel(settings: NotificationSettings, entity: str) -> tuple[int | None, int | None]:
    """
    Get telegram chat_id and topic_id for an entity with fallback.

    Chat_id and topic_id are always paired together - never mix fallback chat_id
    with entity-specific topic_id or vice versa.

    Args:
        settings: NotificationSettings object
        entity: Entity name (admin/core/group/host/node/user/user_template)

    Returns:
        tuple: (chat_id, topic_id) - always paired from same source

    Examples:
        >>> # Entity has its own channel configured
        >>> get_telegram_channel(settings, "admin")
        (123456, 789)  # Uses admin-specific channel

        >>> # Entity has no channel, uses fallback
        >>> get_telegram_channel(settings, "core")
        (999999, None)  # Uses fallback channel
    """
    entity_channel = getattr(settings.channels, entity, None)

    if entity_channel and entity_channel.telegram_chat_id:
        # Use object-specific channel (chat_id + its topic_id)
        return entity_channel.telegram_chat_id, entity_channel.telegram_topic_id
    else:
        # Use fallback (fallback chat_id + its topic_id)
        return settings.telegram_chat_id, settings.telegram_topic_id


def get_discord_webhook(settings: NotificationSettings, entity: str) -> str | None:
    """
    Get discord webhook URL for an entity with fallback.

    Args:
        settings: NotificationSettings object
        entity: Entity name (admin/core/group/host/node/user/user_template)

    Returns:
        str | None: Discord webhook URL

    Examples:
        >>> # Entity has its own webhook configured
        >>> get_discord_webhook(settings, "user")
        'https://discord.com/api/webhooks/123/abc'

        >>> # Entity has no webhook, uses fallback
        >>> get_discord_webhook(settings, "node")
        'https://discord.com/api/webhooks/999/xyz'
    """
    entity_channel = getattr(settings.channels, entity, None)

    if entity_channel and entity_channel.discord_webhook_url:
        return entity_channel.discord_webhook_url
    else:
        return settings.discord_webhook_url


def should_send_admin_notification(admin: AdminContactInfo, action: str) -> bool:
    """
    Check if admin wants to receive this user notification type.

    Args:
        admin: AdminContactInfo object containing notification preferences
        action: Notification action type (create, modify, delete, status_change,
                reset_data_usage, data_reset_by_next, subscription_revoked)

    Returns:
        bool: True if admin wants to receive this notification, False otherwise

    Examples:
        >>> # Admin has no preferences configured (None), receives all
        >>> should_send_admin_notification(admin, "create")
        True

        >>> # Admin has preferences, only receives enabled types
        >>> admin.notification_enable.create = False
        >>> should_send_admin_notification(admin, "create")
        False
    """
    if not admin.notification_enable:
        # None means receive all notifications (backward compatible)
        return True

    # Check if the specific action is enabled in admin preferences
    return getattr(admin.notification_enable, action, True)
