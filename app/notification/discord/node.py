import copy

from app.notification.client import send_discord_webhook
from app.notification.helpers import get_discord_webhook
from app.models.node import NodeNotification, NodeResponse
from app.models.settings import NotificationSettings
from app.settings import notification_settings
from app.utils.helpers import escape_ds_markdown_list, escape_ds_markdown

from . import colors, messages

ENTITY = "node"


async def create_node(node: NodeResponse, by: str):
    name, by = escape_ds_markdown_list((node.name, by))
    message = copy.deepcopy(messages.CREATE_NODE)
    message["description"] = message["description"].format(name=name, address=node.address, port=node.port)
    message["footer"]["text"] = message["footer"]["text"].format(id=node.id, by=by)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.GREEN
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)


async def modify_node(node: NodeResponse, by: str):
    name, by = escape_ds_markdown_list((node.name, by))
    message = copy.deepcopy(messages.MODIFY_NODE)
    message["description"] = message["description"].format(name=name, address=node.address, port=node.port)
    message["footer"]["text"] = message["footer"]["text"].format(id=node.id, by=by)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.YELLOW
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)


async def remove_node(node: NodeResponse, by: str):
    name, by = escape_ds_markdown_list((node.name, by))
    message = copy.deepcopy(messages.REMOVE_NODE)
    message["description"] = message["description"].format(name=name, address=node.address, port=node.port)
    message["footer"]["text"] = message["footer"]["text"].format(id=node.id, by=by)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.RED
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)


async def connect_node(node: NodeNotification):
    name = escape_ds_markdown(node.name)
    message = copy.deepcopy(messages.CONNECT_NODE)
    message["description"] = message["description"].format(
        name=name, node_version=node.node_version, core_version=node.xray_version
    )
    message["footer"]["text"] = message["footer"]["text"].format(id=node.id)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.GREEN
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)


async def error_node(node: NodeNotification):
    name, node_message = escape_ds_markdown_list((node.name, node.message))
    message = copy.deepcopy(messages.ERROR_NODE)
    message["description"] = message["description"].format(name=name, error=node_message)
    message["footer"]["text"] = message["footer"]["text"].format(id=node.id)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.RED
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)
