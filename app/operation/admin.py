import asyncio
from datetime import datetime as dt

from sqlalchemy.exc import IntegrityError

from app import notification
from app.db import AsyncSession
from app.db.crud.admin import (
    AdminsSortingOptions,
    AdminsSortingOptionsSimple,
    create_admin,
    get_admin_usages,
    get_admins,
    get_admins_count,
    get_admins_simple,
    remove_admin,
    reset_admin_usage,
    update_admin,
)
from app.db.crud.bulk import activate_all_disabled_users, disable_all_active_users
from app.db.crud.user import get_users, remove_users
from app.models.admin import AdminCreate, AdminDetails, AdminModify, AdminSimple, AdminsResponse, AdminsSimpleResponse
from app.node.sync import (
    schedule_sync_task,
    sync_remove_users,
    sync_users,
    sync_proto_users,
    remove_user as sync_remove_user,
)
from app.node.user import serialize_users_for_node
from app.models.stats import Period, UserUsageStatsList
from app.operation import BaseOperation, OperatorType
from app.operation.user import UserOperation
from app.utils.logger import get_logger

logger = get_logger("admin-operation")


class AdminOperation(BaseOperation):
    @staticmethod
    def _is_non_blocking_sync_operator(operator_type: OperatorType) -> bool:
        return operator_type in (OperatorType.API, OperatorType.WEB)

    async def create_admin(self, db: AsyncSession, new_admin: AdminCreate, admin: AdminDetails) -> AdminDetails:
        """Create a new admin if the current admin has sudo privileges."""
        try:
            db_admin = await create_admin(db, new_admin)
        except IntegrityError:
            await self.raise_error(message="Admin already exists", code=409, db=db)

        if self.operator_type != OperatorType.CLI:
            logger.info(f'New admin "{db_admin.username}" with id "{db_admin.id}" added by admin "{admin.username}"')
        new_admin = AdminDetails.model_validate(db_admin)
        asyncio.create_task(notification.create_admin(new_admin, admin.username))

        return db_admin

    async def modify_admin(
        self, db: AsyncSession, username: str, modified_admin: AdminModify, current_admin: AdminDetails
    ) -> AdminDetails:
        """Modify an existing admin's details."""
        db_admin = await self.get_validated_admin(db, username=username)
        if self.operator_type != OperatorType.CLI and db_admin.is_sudo:
            await self.raise_error(
                message="You're not allowed to modify sudoer's account. Use pasarguard cli  / tui instead.", code=403
            )

        db_admin = await update_admin(db, db_admin, modified_admin)

        if self.operator_type != OperatorType.CLI:
            logger.info(
                f'Admin "{db_admin.username}" with id "{db_admin.id}" modified by admin "{current_admin.username}"'
            )

        modified_admin = AdminDetails.model_validate(db_admin)
        asyncio.create_task(notification.modify_admin(modified_admin, current_admin.username))
        return modified_admin

    async def remove_admin(self, db: AsyncSession, username: str, current_admin: AdminDetails | None = None):
        """Remove an admin from the database."""
        db_admin = await self.get_validated_admin(db, username=username)
        if self.operator_type != OperatorType.CLI and db_admin.is_sudo:
            await self.raise_error(
                message="You're not allowed to remove sudoer's account. Use pasarguard cli / tui instead.", code=403
            )

        await remove_admin(db, db_admin)
        if self.operator_type != OperatorType.CLI:
            logger.info(
                f'Admin "{db_admin.username}" with id "{db_admin.id}" deleted by admin "{current_admin.username}"'
            )
            asyncio.create_task(notification.remove_admin(username, current_admin.username))

    async def get_admins(
        self,
        db: AsyncSession,
        username: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        sort: str | None = None,
    ) -> AdminsResponse:
        sort_list = []
        if sort is not None:
            opts = sort.strip(",").split(",")
            for opt in opts:
                try:
                    enum_member = AdminsSortingOptions[opt]
                    sort_list.append(enum_member.value)
                except KeyError:
                    await self.raise_error(message=f'"{opt}" is not a valid sort option', code=400)

        use_compact = self.operator_type in (OperatorType.API, OperatorType.WEB)
        admins, total, active, disabled = await get_admins(
            db,
            offset,
            limit,
            username,
            sort_list if sort_list else None,
            return_with_count=True,
            compact=use_compact,
        )

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return AdminsResponse(
                admins=admins,
                total=total,
                active=active,
                disabled=disabled,
            )
        return admins  # type: ignore[return-value]

    async def get_admins_simple(
        self,
        db: AsyncSession,
        search: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        sort: str | None = None,
        all: bool = False,
    ) -> AdminsSimpleResponse:
        """Get lightweight admin list with only id and username"""
        sort_list = []
        if sort is not None:
            opts = sort.strip(",").split(",")
            for opt in opts:
                try:
                    enum_member = AdminsSortingOptionsSimple[opt]
                    sort_list.append(enum_member)
                except KeyError:
                    await self.raise_error(message=f'"{opt}" is not a valid sort option', code=400)

        # Call CRUD function
        rows, total = await get_admins_simple(
            db=db,
            offset=offset,
            limit=limit,
            search=search,
            sort=sort_list if sort_list else None,
            skip_pagination=all,
        )

        # Convert tuples to Pydantic models
        admins = [AdminSimple(id=row[0], username=row[1]) for row in rows]

        return AdminsSimpleResponse(admins=admins, total=total)

    async def get_admins_count(self, db: AsyncSession) -> int:
        return await get_admins_count(db)

    async def disable_all_active_users(self, db: AsyncSession, username: str, admin: AdminDetails):
        """Disable all active users under a specific admin"""
        db_admin = await self.get_validated_admin(db, username=username)

        if db_admin.is_sudo:
            await self.raise_error(message="You're not allowed to disable sudo admin users.", code=403)

        await disable_all_active_users(db=db, admin=db_admin)

        users = await get_users(db, admin=db_admin)
        if self._is_non_blocking_sync_operator(self.operator_type):
            proto_users = await serialize_users_for_node(users)
            schedule_sync_task(sync_proto_users(proto_users))
        else:
            await sync_users(users)

        logger.info(f'Admin "{username}" users has been disabled by admin "{admin.username}"')

    async def activate_all_disabled_users(self, db: AsyncSession, username: str, admin: AdminDetails):
        """Enable all active users under a specific admin"""
        db_admin = await self.get_validated_admin(db, username=username)

        if db_admin.is_sudo:
            await self.raise_error(message="You're not allowed to enable sudo admin users.", code=403)

        await activate_all_disabled_users(db=db, admin=db_admin)

        users = await get_users(db, admin=db_admin)
        if self._is_non_blocking_sync_operator(self.operator_type):
            proto_users = await serialize_users_for_node(users)
            schedule_sync_task(sync_proto_users(proto_users))
        else:
            await sync_users(users)

        logger.info(f'Admin "{username}" users has been activated by admin "{admin.username}"')

    async def remove_all_users(self, db: AsyncSession, username: str, admin: AdminDetails) -> int:
        """Delete all users that belong to the specified admin."""
        db_admin = await self.get_validated_admin(db, username=username)
        target_username = db_admin.username

        if self.operator_type != OperatorType.CLI and db_admin.is_sudo:
            await self.raise_error(message="You're not allowed to delete sudo admin users.", code=403)

        users = await get_users(db, admin=db_admin)
        if not users:
            return 0

        user_operation = UserOperation(self.operator_type)
        serialized_users = [
            await user_operation.validate_user(
                db,
                user,
                include_lifetime_used_traffic=False,
            )
            for user in users
        ]

        await remove_users(db, users)

        if self._is_non_blocking_sync_operator(self.operator_type):
            schedule_sync_task(sync_remove_users(serialized_users))
        else:
            for user in serialized_users:
                await sync_remove_user(user)

        for user in serialized_users:
            asyncio.create_task(notification.remove_user(user, admin))

        logger.info(
            f'Admin "{admin.username}" deleted {len(serialized_users)} users belonging to admin "{target_username}"'
        )
        return len(serialized_users)

    async def reset_admin_usage(self, db: AsyncSession, username: str, admin: AdminDetails) -> AdminDetails:
        db_admin = await self.get_validated_admin(db, username=username)

        db_admin = await reset_admin_usage(db, db_admin=db_admin)
        if self.operator_type != OperatorType.CLI:
            logger.info(f'Admin "{username}" usage has been reset by admin "{admin.username}"')

        reseted_admin = AdminDetails.model_validate(db_admin)
        asyncio.create_task(notification.admin_usage_reset(reseted_admin, admin.username))

        return reseted_admin

    async def get_admin_usage(
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
        """Get aggregated usage for an admin's users."""
        start, end = await self.validate_dates(start, end, True)

        if not admin.is_sudo:
            if username != admin.username:
                await self.raise_error(message="You're not allowed", code=403)
            node_id = None
            group_by_node = False

        db_admin = await self.get_validated_admin(db, username=username)

        return await get_admin_usages(
            db=db,
            admin_id=db_admin.id,
            start=start,
            end=end,
            period=period,
            node_id=node_id,
            group_by_node=group_by_node,
        )
