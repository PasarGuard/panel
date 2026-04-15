import asyncio
from datetime import datetime as dt

from sqlalchemy.exc import IntegrityError

from app import notification
from app.db import AsyncSession
from app.db.crud.admin import (
    AdminsSortingOptions,
    AdminsSortingOptionsSimple,
    create_admin,
    find_admins_by_telegram_id,
    get_admin_usages,
    get_admins,
    get_admins_count,
    get_admins_simple,
    remove_admin,
    remove_admins,
    reset_admin_usage,
    update_admin,
)
from app.db.crud.bulk import activate_all_disabled_users, disable_all_active_users
from app.db.crud.user import get_users, remove_users
from app.db.models import Admin
from app.models.admin import (
    AdminCreate,
    BulkAdminsActionResponse,
    AdminDetails,
    AdminModify,
    AdminSimple,
    AdminsResponse,
    AdminsSimpleResponse,
    BulkAdminSelection,
    RemoveAdminsResponse,
)
from app.node.sync import (
    sync_users,
    remove_user as sync_remove_user,
)
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
        if self.operator_type != OperatorType.CLI and new_admin.is_sudo:
            await self.raise_error(
                message="Creating sudo admin via API is not allowed. Use pasarguard cli / tui.", code=403
            )

        if new_admin.telegram_id is not None:
            existing_admins = await find_admins_by_telegram_id(db, new_admin.telegram_id, limit=1)
            if existing_admins:
                await self.raise_error(message="Telegram ID is already assigned to another admin.", code=409, db=db)

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
        if self.operator_type != OperatorType.CLI and not db_admin.is_sudo and modified_admin.is_sudo:
            await self.raise_error(
                message="Promoting admin to sudo via API is not allowed. Use pasarguard cli / tui instead.", code=403
            )

        if self.operator_type != OperatorType.CLI and db_admin.is_sudo and db_admin.username != current_admin.username:
            await self.raise_error(
                message="You're not allowed to modify sudoer's account. Use pasarguard cli  / tui instead.", code=403
            )

        if db_admin.username == current_admin.username and modified_admin.is_disabled is True:
            await self.raise_error(message="You're not allowed to disable your own account.", code=403)

        if modified_admin.telegram_id is not None:
            existing_admins = await find_admins_by_telegram_id(
                db, modified_admin.telegram_id, exclude_admin_id=db_admin.id, limit=1
            )
            if existing_admins:
                await self.raise_error(message="Telegram ID is already assigned to another admin.", code=409, db=db)

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
        await sync_users(users)

        logger.info(f'Admin "{username}" users has been disabled by admin "{admin.username}"')

    async def activate_all_disabled_users(self, db: AsyncSession, username: str, admin: AdminDetails):
        """Enable all active users under a specific admin"""
        db_admin = await self.get_validated_admin(db, username=username)

        if db_admin.is_sudo:
            await self.raise_error(message="You're not allowed to enable sudo admin users.", code=403)

        await activate_all_disabled_users(db=db, admin=db_admin)

        users = await get_users(db, admin=db_admin)
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
        serialized_users = [await user_operation.validate_user(user) for user in users]

        await remove_users(db, users)
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

    async def bulk_remove_admins(
        self, db: AsyncSession, bulk_admins: BulkAdminSelection, admin: AdminDetails
    ) -> RemoveAdminsResponse:
        """Remove multiple admins by username"""
        db_admins = []
        for username in bulk_admins.usernames:
            db_admin = await self.get_validated_admin(db, username)
            if self.operator_type != OperatorType.CLI and db_admin.is_sudo:
                await self.raise_error(
                    message=f"You're not allowed to remove sudo admin {username}. Use pasarguard cli / tui instead.",
                    code=403,
                )
            db_admins.append(db_admin)

        usernames = [admin_obj.username for admin_obj in db_admins]
        admin_ids = [admin_obj.id for admin_obj in db_admins]

        # Batch delete using CRUD function
        await remove_admins(db, admin_ids)

        if self.operator_type != OperatorType.CLI:
            for username in usernames:
                logger.info(f'Admin "{username}" deleted by admin "{admin.username}"')
                asyncio.create_task(notification.remove_admin(username, admin.username))

        return RemoveAdminsResponse(admins=usernames, count=len(db_admins))

    @staticmethod
    def _build_bulk_action_response(admins: list[AdminDetails | AdminSimple | Admin]) -> BulkAdminsActionResponse:
        usernames = [admin.username for admin in admins]
        return BulkAdminsActionResponse(admins=usernames, count=len(usernames))

    async def _get_validated_bulk_admins(
        self,
        db: AsyncSession,
        usernames: list[str] | set[str],
    ) -> list[Admin]:
        db_admins: list[Admin] = []
        for username in usernames:
            db_admins.append(await self.get_validated_admin(db, username=username))
        return db_admins

    async def _ensure_can_change_admin_status(
        self,
        db_admin: Admin,
        current_admin: AdminDetails,
        *,
        is_disabled: bool,
    ) -> None:
        if self.operator_type != OperatorType.CLI and db_admin.is_sudo and db_admin.username != current_admin.username:
            await self.raise_error(
                message="You're not allowed to modify sudoer's account. Use pasarguard cli  / tui instead.",
                code=403,
            )

        if is_disabled and db_admin.username == current_admin.username:
            await self.raise_error(message="You're not allowed to disable your own account.", code=403)

    async def _ensure_can_manage_admin_users(self, db_admin: Admin, *, action: str) -> None:
        if not db_admin.is_sudo:
            return

        messages = {
            "disable": "You're not allowed to disable sudo admin users.",
            "activate": "You're not allowed to enable sudo admin users.",
            "remove": "You're not allowed to delete sudo admin users.",
        }
        await self.raise_error(message=messages[action], code=403)

    async def bulk_set_admins_disabled(
        self,
        db: AsyncSession,
        bulk_admins: BulkAdminSelection,
        current_admin: AdminDetails,
        *,
        is_disabled: bool,
    ) -> BulkAdminsActionResponse:
        db_admins = await self._get_validated_bulk_admins(db, bulk_admins.usernames)

        for db_admin in db_admins:
            await self._ensure_can_change_admin_status(db_admin, current_admin, is_disabled=is_disabled)

        admins_to_update = [db_admin for db_admin in db_admins if db_admin.is_disabled != is_disabled]

        for db_admin in admins_to_update:
            db_admin.is_disabled = is_disabled

        await db.commit()

        for db_admin in admins_to_update:
            modified_admin = AdminDetails.model_validate(db_admin)
            asyncio.create_task(notification.modify_admin(modified_admin, current_admin.username))
            logger.info(
                f'Admin "{db_admin.username}" bulk {"disabled" if is_disabled else "enabled"} by admin "{current_admin.username}"'
            )

        return self._build_bulk_action_response(admins_to_update)

    async def bulk_reset_admins_usage(
        self, db: AsyncSession, bulk_admins: BulkAdminSelection, admin: AdminDetails
    ) -> BulkAdminsActionResponse:
        db_admins = await self._get_validated_bulk_admins(db, bulk_admins.usernames)

        for db_admin in db_admins:
            db_admin = await reset_admin_usage(db, db_admin=db_admin)
            reseted_admin = AdminDetails.model_validate(db_admin)
            asyncio.create_task(notification.admin_usage_reset(reseted_admin, admin.username))
            logger.info(f'Admin "{db_admin.username}" usage has been reset by admin "{admin.username}"')

        return self._build_bulk_action_response(db_admins)

    async def bulk_disable_all_active_users_for_admins(
        self, db: AsyncSession, bulk_admins: BulkAdminSelection, admin: AdminDetails
    ) -> BulkAdminsActionResponse:
        db_admins = await self._get_validated_bulk_admins(db, bulk_admins.usernames)

        for db_admin in db_admins:
            await self._ensure_can_manage_admin_users(db_admin, action="disable")

        for db_admin in db_admins:
            await self.disable_all_active_users(db, username=db_admin.username, admin=admin)

        return self._build_bulk_action_response(db_admins)

    async def bulk_activate_all_disabled_users_for_admins(
        self, db: AsyncSession, bulk_admins: BulkAdminSelection, admin: AdminDetails
    ) -> BulkAdminsActionResponse:
        db_admins = await self._get_validated_bulk_admins(db, bulk_admins.usernames)

        for db_admin in db_admins:
            await self._ensure_can_manage_admin_users(db_admin, action="activate")

        for db_admin in db_admins:
            await self.activate_all_disabled_users(db, username=db_admin.username, admin=admin)

        return self._build_bulk_action_response(db_admins)

    async def bulk_remove_all_users_for_admins(
        self, db: AsyncSession, bulk_admins: BulkAdminSelection, admin: AdminDetails
    ) -> BulkAdminsActionResponse:
        db_admins = await self._get_validated_bulk_admins(db, bulk_admins.usernames)

        for db_admin in db_admins:
            await self._ensure_can_manage_admin_users(db_admin, action="remove")

        for db_admin in db_admins:
            await self.remove_all_users(db, username=db_admin.username, admin=admin)

        return self._build_bulk_action_response(db_admins)
