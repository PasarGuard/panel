import asyncio
from functools import wraps

from app.models.admin import AdminDetails
from app.models.admin_role import AdminRoleResponse
from app.models.core import CoreResponse
from app.models.group import GroupResponse
from app.models.host import BaseHost
from app.models.node import NodeNotification, NodeResponse
from app.models.api_key import APIKeyResponse
from app.models.user import UserNotificationResponse
from app.models.user_template import UserTemplateResponse
from app.settings import notification_enable
from app.utils.logger import get_logger

from . import discord as ds, telegram as tg, webhook as wh

logger = get_logger("Notification")


async def _gather_notifications(event_name: str, *aws):
    results = await asyncio.gather(*aws, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            logger.warning(
                "Notification channel failed for %s: %s",
                event_name,
                result,
                exc_info=(type(result), result, result.__traceback__),
            )


def _safe_notification_task(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            logger.warning(
                "Notification task %s failed: %s",
                func.__name__,
                err,
                exc_info=(type(err), err, err.__traceback__),
            )

    return wrapper


async def create_api_key(api_key: APIKeyResponse, admin_username: str, by: str):
    if (await notification_enable()).api_key.create:
        await asyncio.gather(
            ds.create_api_key_ds(api_key, admin_username, by), tg.create_api_key_tg(api_key, admin_username, by)
        )


async def modify_api_key(api_key: APIKeyResponse, admin_username: str, by: str):
    if (await notification_enable()).api_key.modify:
        await asyncio.gather(
            ds.modify_api_key_ds(api_key, admin_username, by), tg.modify_api_key_tg(api_key, admin_username, by)
        )


async def remove_api_key(api_key: APIKeyResponse, admin_username: str, by: str):
    if (await notification_enable()).api_key.delete:
        await asyncio.gather(
            ds.remove_api_key_ds(api_key, admin_username, by), tg.remove_api_key_tg(api_key, admin_username, by)
        )


async def create_admin_role(role: AdminRoleResponse, by: str):
    if (await notification_enable()).admin_role.create:
        await _gather_notifications("create_admin_role", ds.create_admin_role(role, by), tg.create_admin_role(role, by))


async def modify_admin_role(role: AdminRoleResponse, by: str):
    if (await notification_enable()).admin_role.modify:
        await _gather_notifications("modify_admin_role", ds.modify_admin_role(role, by), tg.modify_admin_role(role, by))


async def remove_admin_role(role: AdminRoleResponse, by: str):
    if (await notification_enable()).admin_role.delete:
        await _gather_notifications("remove_admin_role", ds.remove_admin_role(role, by), tg.remove_admin_role(role, by))


async def create_host(host: BaseHost, by: str):
    if (await notification_enable()).host.create:
        await _gather_notifications("create_host", ds.create_host(host, by), tg.create_host(host, by))


async def modify_host(host: BaseHost, by: str):
    if (await notification_enable()).host.modify:
        await _gather_notifications("modify_host", ds.modify_host(host, by), tg.modify_host(host, by))


async def remove_host(host: BaseHost, by: str):
    if (await notification_enable()).host.delete:
        await _gather_notifications("remove_host", ds.remove_host(host, by), tg.remove_host(host, by))


async def modify_hosts(by: str):
    if (await notification_enable()).host.modify_hosts:
        await _gather_notifications("modify_hosts", ds.modify_hosts(by), tg.modify_hosts(by))


async def create_user_template(user: UserTemplateResponse, by: str):
    if (await notification_enable()).user_template.create:
        await _gather_notifications(
            "create_user_template", ds.create_user_template(user, by), tg.create_user_template(user, by)
        )


async def modify_user_template(user: UserTemplateResponse, by: str):
    if (await notification_enable()).user_template.modify:
        await _gather_notifications(
            "modify_user_template", ds.modify_user_template(user, by), tg.modify_user_template(user, by)
        )


async def remove_user_template(name: str, by: str):
    if (await notification_enable()).user_template.delete:
        await _gather_notifications(
            "remove_user_template", ds.remove_user_template(name, by), tg.remove_user_template(name, by)
        )


async def create_node(node: NodeResponse, by: str):
    if (await notification_enable()).node.create:
        await _gather_notifications("create_node", ds.create_node(node, by), tg.create_node(node, by))


async def modify_node(node: NodeResponse, by: str):
    if (await notification_enable()).node.modify:
        await _gather_notifications("modify_node", ds.modify_node(node, by), tg.modify_node(node, by))


async def remove_node(node: NodeResponse, by: str):
    if (await notification_enable()).node.delete:
        await _gather_notifications("remove_node", ds.remove_node(node, by), tg.remove_node(node, by))


async def connect_node(node: NodeNotification):
    if (await notification_enable()).node.connect:
        await _gather_notifications("connect_node", ds.connect_node(node), tg.connect_node(node))


async def recovered_node(node: NodeNotification):
    if (await notification_enable()).node.recovered:
        await _gather_notifications("recovered_node", ds.recovered_node(node), tg.recovered_node(node))


async def error_node(node: NodeNotification):
    if (await notification_enable()).node.error:
        await _gather_notifications("error_node", ds.error_node(node), tg.error_node(node))


async def limited_node(node: NodeNotification, data_limit: int, used_traffic: int):
    if (await notification_enable()).node.limited:
        await _gather_notifications(
            "limited_node",
            ds.limited_node(node, data_limit, used_traffic),
            tg.limited_node(node, data_limit, used_traffic),
        )


async def reset_node_usage(node: NodeResponse, by: str, uplink: int, downlink: int):
    if (await notification_enable()).node.reset_usage:
        await _gather_notifications(
            "reset_node_usage",
            ds.reset_node_usage(node, by, uplink, downlink),
            tg.reset_node_usage(node, by, uplink, downlink),
        )


async def create_group(group: GroupResponse, by: str):
    if (await notification_enable()).group.create:
        await _gather_notifications("create_group", ds.create_group(group, by), tg.create_group(group, by))


async def modify_group(group: GroupResponse, by: str):
    if (await notification_enable()).group.modify:
        await _gather_notifications("modify_group", ds.modify_group(group, by), tg.modify_group(group, by))


async def remove_group(group_id: int, by: str):
    if (await notification_enable()).group.delete:
        await _gather_notifications("remove_group", ds.remove_group(group_id, by), tg.remove_group(group_id, by))


async def create_admin(admin: AdminDetails, by: str):
    if (await notification_enable()).admin.create:
        await _gather_notifications("create_admin", ds.create_admin(admin, by), tg.create_admin(admin, by))


async def modify_admin(admin: AdminDetails, by: str):
    if (await notification_enable()).admin.modify:
        await _gather_notifications("modify_admin", ds.modify_admin(admin, by), tg.modify_admin(admin, by))


async def remove_admin(username: str, by: str):
    if (await notification_enable()).admin.delete:
        await _gather_notifications("remove_admin", ds.remove_admin(username, by), tg.remove_admin(username, by))


async def admin_usage_reset(admin: AdminDetails, by: str):
    if (await notification_enable()).admin.reset_usage:
        await _gather_notifications(
            "admin_usage_reset", ds.admin_reset_usage(admin, by), tg.admin_reset_usage(admin, by)
        )


async def admin_usage_limit_reached(admin: AdminDetails, usage_percentage: int, threshold: int):
    if (await notification_enable()).admin.usage_limit_warning:
        await _gather_notifications(
            "admin_usage_limit_reached",
            ds.admin_usage_limit_reached(admin, usage_percentage, threshold),
            tg.admin_usage_limit_reached(admin, usage_percentage, threshold),
        )


async def admin_login(username: str, password: str, client_ip: str, success: bool):
    if (await notification_enable()).admin.login:
        await _gather_notifications(
            "admin_login",
            ds.admin_login(username, password, client_ip, success),
            tg.admin_login(username, password, client_ip, success),
        )


async def user_status_change(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.status_change:
        await _gather_notifications(
            "user_status_change",
            ds.user_status_change(user, by.username),
            tg.user_status_change(user, by.username),
            wh.status_change(user),
        )


async def create_user(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.create:
        await _gather_notifications(
            "create_user",
            ds.create_user(user, by.username),
            tg.create_user(user, by.username),
            wh.notify(wh.UserCreated(username=user.username, user=user, by=by)),
        )


async def modify_user(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.modify:
        await _gather_notifications(
            "modify_user",
            ds.modify_user(user, by.username),
            tg.modify_user(user, by.username),
            wh.notify(wh.UserUpdated(username=user.username, user=user, by=by)),
        )


async def remove_user(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.delete:
        await _gather_notifications(
            "remove_user",
            ds.remove_user(user, by.username),
            tg.remove_user(user, by.username),
            wh.notify(wh.UserDeleted(username=user.username, user=user, by=by)),
        )


async def reset_user_data_usage(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.reset_data_usage:
        await _gather_notifications(
            "reset_user_data_usage",
            ds.reset_user_data_usage(user, by.username),
            tg.reset_user_data_usage(user, by.username),
            wh.notify(wh.UserDataUsageReset(username=user.username, user=user, by=by)),
        )


async def user_data_reset_by_next(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.data_reset_by_next:
        await _gather_notifications(
            "user_data_reset_by_next",
            ds.user_data_reset_by_next(user, by.username),
            tg.user_data_reset_by_next(user, by.username),
            wh.notify(wh.UserDataResetByNext(username=user.username, user=user, by=by)),
        )


async def user_subscription_revoked(user: UserNotificationResponse, by: AdminDetails):
    if (await notification_enable()).user.subscription_revoked:
        await _gather_notifications(
            "user_subscription_revoked",
            ds.user_subscription_revoked(user, by.username),
            tg.user_subscription_revoked(user, by.username),
            wh.notify(wh.UserSubscriptionRevoked(username=user.username, user=user, by=by)),
        )


async def create_core(core: CoreResponse, by: str):
    if (await notification_enable()).core.create:
        await _gather_notifications("create_core", ds.create_core(core, by), tg.create_core(core, by))


async def modify_core(core: CoreResponse, by: str):
    if (await notification_enable()).core.modify:
        await _gather_notifications("modify_core", ds.modify_core(core, by), tg.modify_core(core, by))


async def remove_core(core_id: int, by: str):
    if (await notification_enable()).core.delete:
        await _gather_notifications("remove_core", ds.remove_core(core_id, by), tg.remove_core(core_id, by))


for _task_name in (
    "create_admin_role",
    "modify_admin_role",
    "remove_admin_role",
    "create_host",
    "modify_host",
    "remove_host",
    "modify_hosts",
    "create_user_template",
    "modify_user_template",
    "remove_user_template",
    "create_node",
    "modify_node",
    "remove_node",
    "connect_node",
    "recovered_node",
    "error_node",
    "limited_node",
    "reset_node_usage",
    "create_group",
    "modify_group",
    "remove_group",
    "create_admin",
    "modify_admin",
    "remove_admin",
    "admin_usage_reset",
    "admin_usage_limit_reached",
    "admin_login",
    "user_status_change",
    "create_user",
    "modify_user",
    "remove_user",
    "reset_user_data_usage",
    "user_data_reset_by_next",
    "user_subscription_revoked",
    "create_core",
    "modify_core",
    "remove_core",
):
    globals()[_task_name] = _safe_notification_task(globals()[_task_name])

del _task_name
