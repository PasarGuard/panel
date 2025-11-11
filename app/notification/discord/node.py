import copy

from app.notification.client import send_discord_webhook
from app.notification.helpers import get_discord_webhook
from app.models.node import NodeNotification, NodeResponse
from app.models.settings import NotificationSettings
from app.settings import notification_settings
from app.utils.helpers import escape_ds_markdown_list, escape_ds_markdown
from app.utils.system import readable_size

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


async def limited_node(node: NodeNotification, data_limit: int, used_traffic: int):
    name = escape_ds_markdown(node.name)
    message = copy.deepcopy(messages.LIMITED_NODE)
    message["description"] = message["description"].format(
        name=name, data_limit=readable_size(data_limit), used_traffic=readable_size(used_traffic)
    )
    message["footer"]["text"] = message["footer"]["text"].format(id=node.id)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.YELLOW
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)


async def reset_node_usage(node: NodeResponse, by: str, uplink: int, downlink: int):
    name, by_escaped = escape_ds_markdown_list((node.name, by))
    message = copy.deepcopy(messages.RESET_NODE_USAGE)
    message["description"] = message["description"].format(
        name=name, uplink=readable_size(uplink), downlink=readable_size(downlink)
    )
    message["footer"]["text"] = message["footer"]["text"].format(id=node.id, by=by_escaped)
    data = {
        "content": "",
        "embeds": [message],
    }
    data["embeds"][0]["color"] = colors.BLUE
    settings: NotificationSettings = await notification_settings()
    if settings.notify_discord:
        webhook = get_discord_webhook(settings, ENTITY)
        await send_discord_webhook(data, webhook)
