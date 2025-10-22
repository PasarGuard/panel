import asyncio
import re
import secrets
from collections import Counter
from datetime import datetime as dt, timedelta as td, timezone as tz

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app import notification
from app.db import AsyncSession
from app.db.crud.admin import get_admin
from app.db.crud.bulk import (
    reset_all_users_data_usage,
    update_users_datalimit,
    update_users_expire,
    update_users_proxy_settings,
)
from app.db.crud.user import (
    UsersSortingOptions,
    create_user,
    get_all_users_usages,
    get_expired_users,
    get_user_sub_update_list,
    get_user_subscription_agent_counts,
    get_user_usages,
    get_users,
    modify_user,
    remove_user,
    remove_users,
    reset_user_by_next,
    reset_user_data_usage,
    revoke_user_sub,
    set_owner,
)
from app.db.models import User, UserStatus, UserTemplate
from app.models.admin import AdminDetails
from app.models.stats import Period, UserUsageStatsList
from app.models.user import (
    BulkUser,
    BulkUsersProxy,
    CreateUserFromTemplate,
    ModifyUserByTemplate,
    RemoveUsersResponse,
    UserCreate,
    UserModify,
    UserNotificationResponse,
    UserResponse,
    UsersResponse,
    UserSubscriptionUpdateChart,
    UserSubscriptionUpdateChartSegment,
    UserSubscriptionUpdateList,
)
from app.node import node_manager
from app.operation import BaseOperation, OperatorType
from app.settings import subscription_settings
from app.utils.jwt import create_subscription_token
from app.utils.logger import get_logger
from config import SUBSCRIPTION_PATH

logger = get_logger("user-operation")

_USER_AGENT_SPLIT_RE = re.compile(r"[;/\s\(\)]+")
_VERSION_TOKEN_RE = re.compile(r"v?\d+(?:\.\d+)*", re.IGNORECASE)


class UserOperation(BaseOperation):
    @staticmethod
    async def generate_subscription_url(user: UserNotificationResponse):
        salt = secrets.token_hex(8)
        settings = await subscription_settings()
        url_prefix = (
            user.admin.sub_domain.replace("*", salt)
            if user.admin and user.admin.sub_domain
            else (settings.url_prefix).replace("*", salt)
        )
        token = await create_subscription_token(user.username)
        return f"{url_prefix}/{SUBSCRIPTION_PATH}/{token}"

    async def validate_user(self, db_user: User) -> UserNotificationResponse:
        user = UserNotificationResponse.model_validate(db_user)
        user.subscription_url = await self.generate_subscription_url(user)
        return user

    async def update_user(self, db_user: User) -> UserNotificationResponse:
        user = await self.validate_user(db_user)

        if db_user.status in (UserStatus.active, UserStatus.on_hold):
            user_inbounds = await db_user.inbounds()
            await node_manager.update_user(user, inbounds=user_inbounds)
        else:
            await node_manager.remove_user(user)

        return user

    async def create_user(self, db: AsyncSession, new_user: UserCreate, admin: AdminDetails) -> UserResponse:
        if new_user.next_plan is not None and new_user.next_plan.user_template_id is not None:
            await self.get_validated_user_template(db, new_user.next_plan.user_template_id)

        all_groups = await self.validate_all_groups(db, new_user)
        db_admin = await get_admin(db, admin.username)

        try:
            db_user = await create_user(db, new_user, all_groups, db_admin)
        except IntegrityError:
            await self.raise_error(message="User already exists", code=409, db=db)

        user = await self.update_user(db_user)

        logger.info(f'New user "{db_user.username}" with id "{db_user.id}" added by admin "{admin.username}"')

        asyncio.create_task(notification.create_user(user, admin))

        return user

    async def _modify_user(
        self, db: AsyncSession, db_user: User, modified_user: UserModify, admin: AdminDetails
    ) -> UserResponse:
        if modified_user.group_ids:
            await self.validate_all_groups(db, modified_user)

        if modified_user.next_plan is not None and modified_user.next_plan.user_template_id is not None:
            await self.get_validated_user_template(db, modified_user.next_plan.user_template_id)

        old_status = db_user.status

        db_user = await modify_user(db, db_user, modified_user)
        user = await self.update_user(db_user)

        logger.info(f'User "{user.username}" with id "{db_user.id}" modified by admin "{admin.username}"')

        asyncio.create_task(notification.modify_user(user, admin))

        if user.status != old_status:
            asyncio.create_task(notification.user_status_change(user, admin))

            logger.info(f'User "{db_user.username}" status changed from "{old_status.value}" to "{user.status.value}"')

        return user

    async def modify_user(
        self, db: AsyncSession, username: str, modified_user: UserModify, admin: AdminDetails
    ) -> UserResponse:
        db_user = await self.get_validated_user(db, username, admin)

        return await self._modify_user(db, db_user, modified_user, admin)

    async def remove_user(self, db: AsyncSession, username: str, admin: AdminDetails):
        db_user = await self.get_validated_user(db, username, admin)

        user = await self.validate_user(db_user)
        await remove_user(db, db_user)
        await node_manager.remove_user(user)

        asyncio.create_task(notification.remove_user(user, admin))

        logger.info(f'User "{db_user.username}" with id "{db_user.id}" deleted by admin "{admin.username}"')
        return {}

    async def _reset_user_data_usage(self, db: AsyncSession, db_user: User, admin: AdminDetails):
        old_status = db_user.status

        db_user = await reset_user_data_usage(db=db, db_user=db_user)
        user = await self.update_user(db_user)

        if user.status != old_status:
            asyncio.create_task(notification.user_status_change(user, admin))

        asyncio.create_task(notification.reset_user_data_usage(user, admin))

        logger.info(f'User "{db_user.username}" usage was reset by admin "{admin.username}"')

        return user

    async def reset_user_data_usage(self, db: AsyncSession, username: str, admin: AdminDetails):
        db_user = await self.get_validated_user(db, username, admin)

        return await self._reset_user_data_usage(db, db_user, admin)

    async def revoke_user_sub(self, db: AsyncSession, username: str, admin: AdminDetails) -> UserResponse:
        db_user = await self.get_validated_user(db, username, admin)

        db_user = await revoke_user_sub(db=db, db_user=db_user)
        user = await self.update_user(db_user)

        asyncio.create_task(notification.user_subscription_revoked(user, admin))

        logger.info(f'User "{db_user.username}" subscription was revoked by admin "{admin.username}"')

        return user

    async def reset_users_data_usage(self, db: AsyncSession, admin: AdminDetails):
        """Reset all users data usage"""
        db_admin = await self.get_validated_admin(db, admin.username)
        await reset_all_users_data_usage(db=db, admin=db_admin)

    async def active_next_plan(self, db: AsyncSession, username: str, admin: AdminDetails) -> UserResponse:
        """Reset user by next plan"""
        db_user = await self.get_validated_user(db, username, admin)

        if db_user is None or db_user.next_plan is None:
            await self.raise_error(message="User doesn't have next plan", code=404)

        old_status = db_user.status

        db_user = await reset_user_by_next(db=db, db_user=db_user)

        user = await self.update_user(db_user)

        if user.status != old_status:
            asyncio.create_task(notification.user_status_change(user, admin))

        asyncio.create_task(notification.user_data_reset_by_next(user, admin))

        logger.info(f'User "{db_user.username}"\'s usage was reset by next plan by admin "{admin.username}"')

        return user

    async def set_owner(
        self, db: AsyncSession, username: str, admin_username: str, admin: AdminDetails
    ) -> UserResponse:
        """Set a new owner (admin) for a user."""
        new_admin = await self.get_validated_admin(db, username=admin_username)
        db_user = await self.get_validated_user(db, username, admin)

        db_user = await set_owner(db, db_user, new_admin)
        user = await self.validate_user(db_user)
        logger.info(f'{user.username}"owner successfully set to{new_admin.username} by admin "{admin.username}"')

        return user

    async def get_user_usage(
        self,
        db: AsyncSession,
        username: str,
        admin: AdminDetails,
        start: dt = None,
        end: dt = None,
        period: Period = Period.hour,
        node_id: int | None = None,
        group_by_node: bool = False,
    ) -> UserUsageStatsList:
        start, end = await self.validate_dates(start, end)
        db_user = await self.get_validated_user(db, username, admin)

        if not admin.is_sudo:
            node_id = None
            group_by_node = False

        return await get_user_usages(db, db_user.id, start, end, period, node_id=node_id, group_by_node=group_by_node)

    async def get_user(self, db: AsyncSession, username: str, admin: AdminDetails) -> UserNotificationResponse:
        db_user = await self.get_validated_user(db, username, admin)
        return await self.validate_user(db_user)

    async def get_user_by_id(self, db: AsyncSession, user_id: int, admin: AdminDetails) -> UserNotificationResponse:
        db_user = await self.get_validated_user_by_id(db, user_id, admin)
        return await self.validate_user(db_user)

    async def get_users(
        self,
        db: AsyncSession,
        admin: AdminDetails,
        offset: int = None,
        limit: int = None,
        username: list[str] = None,
        search: str | None = None,
        owner: list[str] | None = None,
        status: UserStatus | None = None,
        sort: str | None = None,
        proxy_id: str | None = None,
        load_sub: bool = False,
        group_ids: list[int] | None = None,
    ) -> UsersResponse:
        """Get all users"""
        sort_list = []
        if sort is not None:
            opts = sort.strip(",").split(",")
            for opt in opts:
                try:
                    enum_member = UsersSortingOptions[opt]
                    sort_list.append(enum_member.value)
                except KeyError:
                    await self.raise_error(message=f'"{opt}" is not a valid sort option', code=400)

        users, count = await get_users(
            db=db,
            offset=offset,
            limit=limit,
            search=search,
            usernames=username,
            status=status,
            sort=sort_list,
            proxy_id=proxy_id,
            admins=owner if admin.is_sudo else [admin.username],
            return_with_count=True,
            group_ids=group_ids,
        )

        if load_sub:
            tasks = [self.generate_subscription_url(user) for user in users]
            urls = await asyncio.gather(*tasks)

            for user, url in zip(users, urls):
                user.subscription_url = url

        response = UsersResponse(users=users, total=count)

        return response

    async def get_users_usage(
        self,
        db: AsyncSession,
        admin: AdminDetails,
        start: dt = None,
        end: dt = None,
        owner: list[str] | None = None,
        period: Period = Period.hour,
        node_id: int | None = None,
        group_by_node: bool = False,
    ) -> UserUsageStatsList:
        """Get all users usage"""
        start, end = await self.validate_dates(start, end)

        if not admin.is_sudo:
            node_id = None
            group_by_node = False

        return await get_all_users_usages(
            db=db,
            start=start,
            end=end,
            period=period,
            node_id=node_id,
            admin=owner if admin.is_sudo else [admin.username],
            group_by_node=group_by_node,
        )

    @staticmethod
    async def remove_users_logger(users: list[str], by: str):
        for user in users:
            logger.info(f'User "{user}" deleted by admin "{by}"')

    async def get_expired_users(
        self,
        db: AsyncSession,
        expired_after: dt = None,
        expired_before: dt = None,
        admin_username: str = None,
    ) -> list[str]:
        """
        Get users who have expired within the specified date range.

        - **expired_after** UTC datetime (optional)
        - **expired_before** UTC datetime (optional)
        - At least one of expired_after or expired_before must be provided for filtering
        - If both are omitted, returns all expired users
        """

        expired_after, expired_before = await self.validate_dates(expired_after, expired_before)
        if admin_username:
            admin_id = (await self.get_validated_admin(db, admin_username)).id
        else:
            admin_id = None
        users = await get_expired_users(db, expired_after, expired_before, admin_id)
        return [row.username for row in users]

    async def delete_expired_users(
        self,
        db: AsyncSession,
        admin: AdminDetails,
        expired_after: dt = None,
        expired_before: dt = None,
        admin_username: str = None,
    ) -> RemoveUsersResponse:
        """
        Delete users who have expired within the specified date range.

        - **expired_after** UTC datetime (optional)
        - **expired_before** UTC datetime (optional)
        - At least one of expired_after or expired_before must be provided
        """

        expired_after, expired_before = await self.validate_dates(expired_after, expired_before)
        if admin_username:
            admin_id = (await self.get_validated_admin(db, admin_username)).id
        else:
            admin_id = None
        users = await get_expired_users(db, expired_after, expired_before, admin_id)
        await remove_users(db, users)

        username_list = [row.username for row in users]
        self.remove_users_logger(users=username_list, by=admin.username)

        return RemoveUsersResponse(users=username_list, count=len(username_list))

    @staticmethod
    def load_base_user_args(template: UserTemplate) -> dict:
        user_args = {
            "data_limit": template.data_limit,
            "group_ids": template.group_ids,
            "data_limit_reset_strategy": template.data_limit_reset_strategy,
            "status": template.status,
        }

        if template.status == UserStatus.active:
            if template.expire_duration:
                user_args["expire"] = dt.now(tz.utc) + td(seconds=template.expire_duration)
            else:
                user_args["expire"] = 0
        else:
            user_args["expire"] = 0
            user_args["on_hold_expire_duration"] = template.expire_duration
            if template.on_hold_timeout:
                user_args["on_hold_timeout"] = dt.now(tz.utc) + td(seconds=template.on_hold_timeout)
            else:
                user_args["on_hold_timeout"] = 0

        return user_args

    @staticmethod
    def apply_settings(user_args: UserCreate | UserModify, template: UserTemplate) -> dict:
        if template.extra_settings:
            flow = template.extra_settings.get("flow", None)
            method = template.extra_settings.get("method", None)

            if flow is not None:
                user_args.proxy_settings.vless.flow = flow

            if method is not None:
                user_args.proxy_settings.shadowsocks.method = method

        return user_args

    async def create_user_from_template(
        self, db: AsyncSession, new_template_user: CreateUserFromTemplate, admin: AdminDetails
    ) -> UserResponse:
        user_template = await self.get_validated_user_template(db, new_template_user.user_template_id)

        if user_template.is_disabled:
            await self.raise_error("this template is disabled", 403)

        new_user_args = self.load_base_user_args(user_template)
        new_user_args["username"] = (
            f"{user_template.username_prefix if user_template.username_prefix else ''}{new_template_user.username}{user_template.username_suffix if user_template.username_suffix else ''}"
        )

        try:
            new_user = UserCreate(**new_user_args, note=new_template_user.note)
        except ValidationError as e:
            error_messages = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
            await self.raise_error(message=error_messages, code=400)

        new_user = self.apply_settings(new_user, user_template)

        return await self.create_user(db, new_user, admin)

    async def modify_user_with_template(
        self, db: AsyncSession, username: str, modified_template: ModifyUserByTemplate, admin: AdminDetails
    ) -> UserResponse:
        db_user = await self.get_validated_user(db, username, admin)
        user_template = await self.get_validated_user_template(db, modified_template.user_template_id)

        if user_template.is_disabled:
            await self.raise_error("this template is disabled", 403)

        user_args = self.load_base_user_args(user_template)
        user_args["proxy_settings"] = db_user.proxy_settings

        try:
            modify_user = UserModify(**user_args, note=modified_template.note)
        except ValidationError as e:
            error_messages = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
            await self.raise_error(message=error_messages, code=400)

        modify_user = self.apply_settings(modify_user, user_template)

        if user_template.reset_usages:
            await self._reset_user_data_usage(db, db_user, admin)

        return await self._modify_user(db, db_user, modify_user, admin)

    async def bulk_modify_expire(self, db: AsyncSession, bulk_model: BulkUser):
        users, users_count = await update_users_expire(db, bulk_model)

        await node_manager.update_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return {"detail": f"operation has been successfuly done on {users_count} users"}
        return users_count

    async def bulk_modify_datalimit(self, db: AsyncSession, bulk_model: BulkUser):
        users, users_count = await update_users_datalimit(db, bulk_model)

        await node_manager.update_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return {"detail": f"operation has been successfuly done on {users_count} users"}
        return users_count

    async def bulk_modify_proxy_settings(self, db: AsyncSession, bulk_model: BulkUsersProxy):
        users, users_count = await update_users_proxy_settings(db, bulk_model)

        await node_manager.update_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return {"detail": f"operation has been successfuly done on {users_count} users"}
        return users_count

    async def get_user_sub_update_list(
        self, db: AsyncSession, username: str, admin: AdminDetails, offset: int = 0, limit: int = 10
    ) -> UserSubscriptionUpdateList:
        db_user = await self.get_validated_user(db, username, admin)
        user_sub_data, count = await get_user_sub_update_list(db, user_id=db_user.id, offset=offset, limit=limit)

        return UserSubscriptionUpdateList(updates=user_sub_data, count=count)

    async def get_user_sub_update_chart(
        self,
        db: AsyncSession,
        admin: AdminDetails,
        username: str | None = None,
        admin_id: int | None = None,
    ) -> UserSubscriptionUpdateChart:
        if username:
            db_user = await self.get_validated_user(db, username, admin)
            agent_counts = await get_user_subscription_agent_counts(db, user_id=db_user.id)
            return self._build_user_agent_chart(agent_counts)

        if admin_id:
            if not admin.is_sudo and admin_id != admin.id:
                await self.raise_error(message="You're not allowed", code=403)
            elif admin.is_sudo and admin_id != admin.id:
                await self.get_validated_admin_by_id(db, admin_id)
        else:
            admin_id = None if admin.is_sudo else admin.id

        agent_counts = await get_user_subscription_agent_counts(db, admin_id=admin_id)
        return self._build_user_agent_chart(agent_counts)

    @classmethod
    def _build_user_agent_chart(cls, agent_counts: list[tuple[str, int]]) -> UserSubscriptionUpdateChart:
        if not agent_counts:
            return UserSubscriptionUpdateChart(total=0, segments=[])

        counts = Counter()
        display_names: dict[str, str] = {}

        for agent, count in agent_counts:
            normalized = cls._normalize_user_agent(agent)
            key = normalized.lower()
            counts[key] += count
            display_names.setdefault(key, normalized)

        total = sum(counts.values())
        segments = [
            UserSubscriptionUpdateChartSegment(
                name=display_names[key],
                count=count,
                percentage=round((count / total) * 100, 2) if total else 0.0,
            )
            for key, count in counts.most_common()
        ]

        return UserSubscriptionUpdateChart(total=total, segments=segments)

    @staticmethod
    def _normalize_user_agent(user_agent: str) -> str:
        if not user_agent:
            return "Unknown"

        cleaned = user_agent.strip()
        if not cleaned:
            return "Unknown"

        tokens = [token for token in _USER_AGENT_SPLIT_RE.split(cleaned) if token]

        for token in tokens:
            if _VERSION_TOKEN_RE.fullmatch(token):
                continue

            sanitized = token.strip("-_")
            if sanitized:
                return sanitized

        return "Unknown"
