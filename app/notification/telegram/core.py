from html import escape

from app.notification.client import send_telegram_message
from app.notification.helpers import get_telegram_channel
from app.models.core import CoreResponse
from app.models.settings import NotificationSettings
from app.settings import notification_settings

from .utils import escape_html_core
from . import messages

ENTITY = "core"


async def create_core(core: CoreResponse, by: str):
    name, exclude_tags, fallback_tags, by = escape_html_core(core, by)
    data = messages.CREATE_CORE.format(
        name=name, exclude_inbound_tags=exclude_tags, fallbacks_inbound_tags=fallback_tags, id=core.id, by=by
    )
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)


async def modify_core(core: CoreResponse, by: str):
    name, exclude_tags, fallback_tags, by = escape_html_core(core, by)
    data = messages.MODIFY_CORE.format(
        name=name,
        exclude_inbound_tags=exclude_tags,
        fallbacks_inbound_tags=fallback_tags,
        id=core.id,
        by=by,
    )
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)


async def remove_core(core_id: int, by: str):
    data = messages.REMOVE_CORE.format(id=core_id, by=escape(by))
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)
