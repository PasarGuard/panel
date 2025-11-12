import asyncio

from . import discord as ds
from . import telegram as tg
from . import webhook as wh
from app.models.host import BaseHost
from app.models.user_template import UserTemplateResponse
from app.models.node import NodeNotification, NodeResponse
from app.models.group import GroupResponse
from app.models.core import CoreResponse
from app.models.admin import AdminDetails
from app.models.user import UserNotificationResponse
from app.settings import notification_enable


async def create_host(host: BaseHost, by: str):
    if (await notification_enable()).host.create:
        await asyncio.gather(ds.create_host(host, by), tg.create_host(host, by))


async def modify_host(host: BaseHost, by: str):
    if (await notification_enable()).host.modify:
        await asyncio.gather(ds.modify_host(host, by), tg.modify_host(host, by))


async def remove_host(host: BaseHost, by: str):
    if (await notification_enable()).host.delete:
        await asyncio.gather(ds.remove_host(host, by), tg.remove_host(host, by))


async def modify_hosts(by: str):
    if (await notification_enable()).host.modify_hosts:
        await asyncio.gather(ds.modify_hosts(by), tg.modify_hosts(by))


async def create_user_template(user: UserTemplateResponse, by: str):
    if (await notification_enable()).user_template.create:
        await asyncio.gather(ds.create_user_template(user, by), tg.create_user_template(user, by))


async def modify_user_template(user: UserTemplateResponse, by: str):
    if (await notification_enable()).user_template.modify:
        await asyncio.gather(ds.modify_user_template(user, by), tg.modify_user_template(user, by))


async def remove_user_template(name: str, by: str):
    if (await notification_enable()).user_template.delete:
        await asyncio.gather(ds.remove_user_template(name, by), tg.remove_user_template(name, by))


async def create_node(node: NodeResponse, by: str):
    if (await notification_enable()).node.create:
        await asyncio.gather(ds.create_node(node, by), tg.create_node(node, by))


async def modify_node(node: NodeResponse, by: str):
    if (await notification_enable()).node.modify:
        await asyncio.gather(ds.modify_node(node, by), tg.modify_node(node, by))


async def remove_node(node: NodeResponse, by: str):
    if (await notification_enable()).node.delete:
        await asyncio.gather(ds.remove_node(node, by), tg.remove_node(node, by))


async def connect_node(node: NodeNotification):
    if (await notification_enable()).node.connect:
        await asyncio.gather(ds.connect_node(node), tg.connect_node(node))


async def error_node(node: NodeNotification):
    if (await notification_enable()).node.error:
        await asyncio.gather(ds.error_node(node), tg.error_node(node))


async def limited_node(node: NodeNotification, data_limit: int, used_traffic: int):
    if (await notification_enable()).node.limited:
        await asyncio.gather(
            ds.limited_node(node, data_limit, used_traffic), tg.limited_node(node, data_limit, used_traffic)
        )


async def reset_node_usage(node: NodeResponse, by: str, uplink: int, downlink: int):
    if (await notification_enable()).node.reset_usage:
        await asyncio.gather(
            ds.reset_node_usage(node, by, uplink, downlink), tg.reset_node_usage(node, by, uplink, downlink)
        )


async def create_group(group: GroupResponse, by: str):
    if (await notification_enable()).group.create:
        await asyncio.gather(ds.create_group(group, by), tg.create_group(group, by))


async def modify_group(group: GroupResponse, by: str):
    if (await notification_enable()).group.modify:
        await asyncio.gather(ds.modify_group(group, by), tg.modify_group(group, by))


async def remove_group(group_id: int, by: str):
    if (await notification_enable()).group.delete:
        await asyncio.gather(ds.remove_group(group_id, by), tg.remove_group(group_id, by))


async def create_admin(admin: AdminDetails, by: str):
    if (await notification_enable()).admin.create:
        await asyncio.gather(ds.create_admin(admin, by), tg.create_admin(admin, by))


async def modify_admin(admin: AdminDetails, by: str):
    if (await notification_enable()).admin.modify:
        await asyncio.gather(ds.modify_admin(admin, by), tg.modify_admin(admin, by))


async def remove_admin(username: str, by: str):
    if (await notification_enable()).admin.delete:
        await asyncio.gather(ds.remove_admin(username, by), tg.remove_admin(username, by))


async def admin_usage_reset(admin: AdminDetails, by: str):
    if (await notification_enable()).admin.reset_usage:
        await asyncio.gather(ds.admin_reset_usage(admin, by), tg.admin_reset_usage(admin, by))


async def admin_login(username: str, password: str, client_ip: str, success: bool):
    if (await notification_enable()).admin.login:
        await asyncio.gather(
            ds.admin_login(username, password, client_ip, success),
            tg.admin_login(username, password, client_ip, success),
        )


async def user_status_change(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.status_change:
        await asyncio.gather(
            ds.user_status_change(user, by.username), tg.user_status_change(user, by.username), wh.status_change(user)
        )


async def create_user(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.create:
        await asyncio.gather(
            ds.create_user(user, by.username),
            tg.create_user(user, by.username),
            wh.notify(wh.UserCreated(username=user.username, user=user, by=by)),
        )


async def modify_user(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.modify:
        await asyncio.gather(
            ds.modify_user(user, by.username),
            tg.modify_user(user, by.username),
            wh.notify(wh.UserUpdated(username=user.username, user=user, by=by)),
        )


async def remove_user(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.delete:
        await asyncio.gather(
            ds.remove_user(user, by.username),
            tg.remove_user(user, by.username),
            wh.notify(wh.UserDeleted(username=user.username, user=user, by=by)),
        )


async def reset_user_data_usage(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.reset_data_usage:
        await asyncio.gather(
            ds.reset_user_data_usage(user, by.username),
            tg.reset_user_data_usage(user, by.username),
            wh.notify(wh.UserDataUsageReset(username=user.username, user=user, by=by)),
        )


async def user_data_reset_by_next(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.data_reset_by_next:
        await asyncio.gather(
            ds.user_data_reset_by_next(user, by.username),
            tg.user_data_reset_by_next(user, by.username),
            wh.notify(wh.UserDataResetByNext(username=user.username, user=user, by=by)),
        )


async def user_subscription_revoked(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.subscription_revoked:
        await asyncio.gather(
            ds.user_subscription_revoked(user, by.username),
            tg.user_subscription_revoked(user, by.username),
            wh.notify(wh.UserSubscriptionRevoked(username=user.username, user=user, by=by)),
        )


async def create_core(core: CoreResponse, by: str):
    if (await notification_enable()).core.create:
        await asyncio.gather(ds.create_core(core, by), tg.create_core(core, by))


async def modify_core(core: CoreResponse, by: str):
    if (await notification_enable()).core.modify:
        await asyncio.gather(ds.modify_core(core, by), tg.modify_core(core, by))


async def remove_core(core_id: int, by: str):
    if (await notification_enable()).core.delete:
        await asyncio.gather(ds.remove_core(core_id, by), tg.remove_core(core_id, by))
