from html import escape

from app.notification.client import send_telegram_message
from app.notification.helpers import get_telegram_channel
from app.models.node import NodeNotification, NodeResponse
from app.models.settings import NotificationSettings
from app.settings import notification_settings
from app.utils.helpers import escape_tg_html
from . import messages

ENTITY = "node"


async def create_node(node: NodeResponse, by: str):
    name, by = escape_tg_html((node.name, by))
    data = messages.CREATE_NODE.format(id=node.id, name=name, address=node.address, port=node.port, by=by)
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)


async def modify_node(node: NodeResponse, by: str):
    name, by = escape_tg_html((node.name, by))
    data = messages.MODIFY_NODE.format(id=node.id, name=name, address=node.address, port=node.port, by=by)
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)


async def remove_node(node: NodeResponse, by: str):
    name, by = escape_tg_html((node.name, by))
    data = messages.REMOVE_NODE.format(id=node.id, name=name, by=by)
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)


async def connect_node(node: NodeNotification):
    data = messages.CONNECT_NODE.format(
        name=escape(node.name), node_version=node.node_version, core_version=node.xray_version, id=node.id
    )
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)


async def error_node(node: NodeNotification):
    name, message = escape_tg_html((node.name, node.message))
    data = messages.ERROR_NODE.format(name=name, error=message, id=node.id)
    settings: NotificationSettings = await notification_settings()
    if settings.notify_telegram:
        chat_id, topic_id = get_telegram_channel(settings, ENTITY)
        await send_telegram_message(data, chat_id, topic_id)
