import asyncio
import warnings
from datetime import datetime as dt

from sqlalchemy.exc import IntegrityError

from app import notification
from app.db import AsyncSession
from app.db.crud.admin import (
    build_admin_details,
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
from app.db.models import Admin, AdminStatus
from app.models.admin import (
    AdminCreate,
    AdminDetails,
    AdminListQuery,
    AdminModify,
    AdminSimple,
    AdminSimpleListQuery,
    AdminsResponse,
    AdminsSimpleResponse,
    AdminUsageQuery,
    BulkAdminsActionResponse,
    BulkAdminSelection,
    RemoveAdminsResponse,
)
from app.models.stats import Period, UserUsageStatsList
from app.models.user import UserListQuery
from app.node.sync import remove_user as sync_remove_user, sync_users
from app.operation import BaseOperation
from app.operation.admin_sync import admin_users_sync_blocked, sync_admin_users_for_block_transition
from app.operation.permissions import PermissionDenied, enforce_permission
from app.operation.user import UserOperation
from app.utils.logger import get_logger

logger = get_logger("admin-operation")


class AdminOperation(BaseOperation):
    @staticmethod
    def _is_owner_admin(db_admin: Admin) -> bool:
        return db_admin.role_id == 1

    async def _ensure_owner_target_access(self, db_admin: Admin, current_admin: AdminDetails) -> None:
        if not current_admin.is_owner and self._is_owner_admin(db_admin):
            await self.raise_error(message="Owner account is not accessible.", code=403)

    async def create_admin(self, db: AsyncSession, new_admin: AdminCreate, admin: AdminDetails) -> AdminDetails:
        """Create a new admin."""
        if new_admin.role_id == 1:
            await self.raise_error(
                message="Owner role cannot be assigned via this endpoint. Use the setup flow.", code=403
            )

        if new_admin.telegram_id is not None:
            existing_admins = await find_admins_by_telegram_id(db, new_admin.telegram_id, limit=1)
            if existing_admins:
                await self.raise_error(message="Telegram ID is already assigned to another admin.", code=409, db=db)

        try:
            db_admin = await create_admin(db, new_admin)
        except IntegrityError:
            await self.raise_error(message="Admin already exists", code=409, db=db)

        logger.info(f'New admin "{db_admin.username}" with id "{db_admin.id}" added by admin "{admin.username}"')
        new_admin_details = build_admin_details(db_admin, include_loaded_metrics=True)
        asyncio.create_task(notification.create_admin(new_admin_details, admin.username))
        return db_admin

    async def modify_admin(
        self, db: AsyncSession, username: str, modified_admin: AdminModify, current_admin: AdminDetails
    ) -> AdminDetails:
        warnings.warn(
            "modify_admin(username, ...) is deprecated. Use modify_admin_by_id(admin_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_admin = await self.get_validated_admin(db, username=username)
        await self._ensure_owner_target_access(db_admin, current_admin)
        return await self._modify_admin(db, db_admin, modified_admin, current_admin)

    async def _modify_admin(
        self, db: AsyncSession, db_admin: Admin, modified_admin: AdminModify, current_admin: AdminDetails
    ) -> AdminDetails:
        """Modify an existing admin's details."""
        # Owner can only be modified by themselves via normal routes.
        is_owner_target = self._is_owner_admin(db_admin)
        is_self = current_admin.id is not None and db_admin.id == current_admin.id

        if is_owner_target and not is_self:
            await self.raise_error(message="Owner cannot be modified via this endpoint. Use the setup flow.", code=403)

        if modified_admin.role_id == 1 and not (is_owner_target and is_self and db_admin.role_id == 1):
            await self.raise_error(
                message="Owner role cannot be assigned via this endpoint. Use the setup flow.", code=403
            )

        if is_owner_target and modified_admin.role_id is not None and modified_admin.role_id != db_admin.role_id:
            await self.raise_error(
                message="Owner role cannot be changed via this endpoint. Use the setup flow.", code=403
            )

        if (
            not current_admin.is_owner
            and is_self
            and modified_admin.role_id is not None
            and modified_admin.role_id != db_admin.role_id
        ):
            await self.raise_error(message="You're not allowed to change your own role.", code=403)

        if not current_admin.is_owner and is_self:
            if modified_admin.status is not None and modified_admin.status == AdminStatus.disabled:
                await self.raise_error(message="You're not allowed to disable your own account.", code=403)

        if modified_admin.telegram_id:
            existing_admins = await find_admins_by_telegram_id(
                db, modified_admin.telegram_id, exclude_admin_id=db_admin.id, limit=1
            )
            if existing_admins:
                await self.raise_error(message="Telegram ID is already assigned to another admin.", code=409, db=db)

        old_users_sync_blocked = await admin_users_sync_blocked(db_admin)
        db_admin = await update_admin(db, db_admin, modified_admin)

        # Sync users to nodes if this admin's role/status starts or stops blocking user sync.
        await sync_admin_users_for_block_transition(db, db_admin, old_users_sync_blocked)

        logger.info(f'Admin "{db_admin.username}" with id "{db_admin.id}" modified by admin "{current_admin.username}"')

        modified_admin_details = build_admin_details(db_admin, include_loaded_metrics=True)
        asyncio.create_task(notification.modify_admin(modified_admin_details, current_admin.username))
        return modified_admin_details

    async def modify_admin_by_id(
        self, db: AsyncSession, admin_id: int, modified_admin: AdminModify, current_admin: AdminDetails
    ) -> AdminDetails:
        db_admin = await self.get_validated_admin_by_id(db, admin_id)
        await self._ensure_owner_target_access(db_admin, current_admin)
        return await self._modify_admin(db, db_admin, modified_admin, current_admin)

    async def remove_admin(self, db: AsyncSession, username: str, current_admin: AdminDetails | None = None):
        warnings.warn(
            "remove_admin(username, ...) is deprecated. Use remove_admin_by_id(admin_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_admin = await self.get_validated_admin(db, username=username)
        if current_admin is not None:
            await self._ensure_owner_target_access(db_admin, current_admin)
        await self._remove_admin(db, db_admin, current_admin)

    async def _remove_admin(self, db: AsyncSession, db_admin: Admin, current_admin: AdminDetails | None = None):
        """Remove an admin from the database."""
        if db_admin.role_id == 1:
            await self.raise_error(message="Owner cannot be deleted via this endpoint. Use the setup flow.", code=403)

        await remove_admin(db, db_admin)
        if current_admin:
            logger.info(
                f'Admin "{db_admin.username}" with id "{db_admin.id}" deleted by admin "{current_admin.username}"'
            )
            asyncio.create_task(notification.remove_admin(db_admin.username, current_admin.username))

    async def remove_admin_by_id(self, db: AsyncSession, admin_id: int, current_admin: AdminDetails | None = None):
        db_admin = await self.get_validated_admin_by_id(db, admin_id)
        if current_admin is not None:
            await self._ensure_owner_target_access(db_admin, current_admin)
        await self._remove_admin(db, db_admin, current_admin)

    async def get_admins(self, db: AsyncSession, query: AdminListQuery, admin: AdminDetails) -> AdminsResponse:
        """Retrieve a list of admins with optional filters and pagination."""
        admins, total, active, disabled, limited = await get_admins(
            db,
            query,
            return_with_count=True,
            compact=True,
            include_owner=admin.is_owner,
        )
        return AdminsResponse(admins=admins, total=total, active=active, disabled=disabled, limited=limited)

    async def get_admins_simple(
        self, db: AsyncSession, query: AdminSimpleListQuery, admin: AdminDetails
    ) -> AdminsSimpleResponse:
        """Get lightweight admin list with only id and username."""
        rows, total = await get_admins_simple(db=db, query=query, include_owner=admin.is_owner)
        admins = [AdminSimple(id=row[0], username=row[1]) for row in rows]
        return AdminsSimpleResponse(admins=admins, total=total)

    async def get_admins_count(self, db: AsyncSession) -> int:
        return await get_admins_count(db)

    async def disable_all_active_users(self, db: AsyncSession, username: str, admin: AdminDetails):
        warnings.warn(
            "disable_all_active_users(username, ...) is deprecated. Use disable_all_active_users_by_id(admin_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_admin = await self.get_validated_admin(db, username=username)
        await self._ensure_owner_target_access(db_admin, admin)
        await self._disable_all_active_users_for_admin(db, db_admin, admin)

    async def _disable_all_active_users_for_admin(self, db: AsyncSession, db_admin: Admin, admin: AdminDetails):
        """Disable all active users under a specific admin."""
        await disable_all_active_users(db=db, admin=db_admin)
        users = await get_users(db, query=UserListQuery(), admin=db_admin, load_admin_role=True)
        await sync_users(users)
        logger.info(f'Admin "{db_admin.username}" users has been disabled by admin "{admin.username}"')

    async def disable_all_active_users_by_id(self, db: AsyncSession, admin_id: int, admin: AdminDetails):
        db_admin = await self.get_validated_admin_by_id(db, admin_id)
        await self._ensure_owner_target_access(db_admin, admin)
        await self._disable_all_active_users_for_admin(db, db_admin, admin)

    async def activate_all_disabled_users(self, db: AsyncSession, username: str, admin: AdminDetails):
        warnings.warn(
            "activate_all_disabled_users(username, ...) is deprecated. Use activate_all_disabled_users_by_id(admin_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_admin = await self.get_validated_admin(db, username=username)
        await self._ensure_owner_target_access(db_admin, admin)
        await self._activate_all_disabled_users_for_admin(db, db_admin, admin)

    async def _activate_all_disabled_users_for_admin(self, db: AsyncSession, db_admin: Admin, admin: AdminDetails):
        """Activate all disabled users under a specific admin."""
        await activate_all_disabled_users(db=db, admin=db_admin)
        users = await get_users(db, query=UserListQuery(), admin=db_admin, load_admin_role=True)
        await sync_users(users)
        logger.info(f'Admin "{db_admin.username}" users has been activated by admin "{admin.username}"')

    async def activate_all_disabled_users_by_id(self, db: AsyncSession, admin_id: int, admin: AdminDetails):
        db_admin = await self.get_validated_admin_by_id(db, admin_id)
        await self._ensure_owner_target_access(db_admin, admin)
        await self._activate_all_disabled_users_for_admin(db, db_admin, admin)

    async def remove_all_users(self, db: AsyncSession, username: str, admin: AdminDetails) -> int:
        warnings.warn(
            "remove_all_users(username, ...) is deprecated. Use remove_all_users_by_id(admin_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_admin = await self.get_validated_admin(db, username=username)
        await self._ensure_owner_target_access(db_admin, admin)
        return await self._remove_all_users_for_admin(db, db_admin, admin)

    async def _remove_all_users_for_admin(self, db: AsyncSession, db_admin: Admin, admin: AdminDetails) -> int:
        """Delete all users that belong to the specified admin."""
        users = await get_users(db, query=UserListQuery(), admin=db_admin, load_admin_role=True)
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
            f'Admin "{admin.username}" deleted {len(serialized_users)} users belonging to admin "{db_admin.username}"'
        )
        return len(serialized_users)

    async def remove_all_users_by_id(self, db: AsyncSession, admin_id: int, admin: AdminDetails) -> int:
        db_admin = await self.get_validated_admin_by_id(db, admin_id)
        await self._ensure_owner_target_access(db_admin, admin)
        return await self._remove_all_users_for_admin(db, db_admin, admin)

    async def reset_admin_usage(self, db: AsyncSession, username: str, admin: AdminDetails) -> AdminDetails:
        warnings.warn(
            "reset_admin_usage(username, ...) is deprecated. Use reset_admin_usage_by_id(admin_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_admin = await self.get_validated_admin(db, username=username)
        await self._ensure_owner_target_access(db_admin, admin)
        return await self._reset_admin_usage(db, db_admin, admin)

    async def _reset_admin_usage(self, db: AsyncSession, db_admin: Admin, admin: AdminDetails) -> AdminDetails:
        """Reset an admin's traffic usage and log the action."""
        old_status = db_admin.status
        db_admin = await reset_admin_usage(db, db_admin=db_admin)

        # If admin was limited and is now active, re-sync all users to nodes
        if old_status == AdminStatus.limited and db_admin.status == AdminStatus.active:
            await sync_admin_users_for_block_transition(db, db_admin, was_blocked=True)

        logger.info(f'Admin "{db_admin.username}" usage has been reset by admin "{admin.username}"')
        reseted_admin_details = build_admin_details(db_admin, include_loaded_metrics=True)
        asyncio.create_task(notification.admin_usage_reset(reseted_admin_details, admin.username))
        return reseted_admin_details

    async def reset_admin_usage_by_id(self, db: AsyncSession, admin_id: int, admin: AdminDetails) -> AdminDetails:
        db_admin = await self.get_validated_admin_by_id(db, admin_id)
        await self._ensure_owner_target_access(db_admin, admin)
        return await self._reset_admin_usage(db, db_admin, admin)

    async def get_admin_usage(
        self, db: AsyncSession, username: str, admin: AdminDetails, query: AdminUsageQuery
    ) -> UserUsageStatsList:
        warnings.warn(
            "get_admin_usage(username, ...) is deprecated. Use get_admin_usage_by_id(admin_id, ...).",
            DeprecationWarning,
            stacklevel=2,
        )
        db_admin = await self.get_validated_admin(db, username=username)
        await self._ensure_owner_target_access(db_admin, admin)
        return await self._get_admin_usage(
            db,
            db_admin,
            admin,
            start=query.start,
            end=query.end,
            period=query.period,
            node_id=query.node_id,
            group_by_node=query.group_by_node,
        )

    async def _get_admin_usage(
        self,
        db: AsyncSession,
        db_admin: Admin,
        admin: AdminDetails,
        start: dt = None,
        end: dt = None,
        period: Period = Period.hour,
        node_id: int | None = None,
        group_by_node: bool = False,
    ) -> UserUsageStatsList:
        """Get aggregated usage for an admin's users."""
        start, end = await self.validate_dates(start, end, True)

        is_self = db_admin.username == admin.username
        if not is_self:
            # Non-self access requires admins.read permission
            try:
                enforce_permission(admin, "admins", "read")
            except PermissionDenied:
                await self.raise_error(message="You're not allowed", code=403)
        else:
            # Self-access: restrict to own data only (no cross-node filtering)
            node_id = None
            group_by_node = False

        return await get_admin_usages(
            db=db,
            admin_id=db_admin.id,
            start=start,
            end=end,
            period=period,
            node_id=node_id,
            group_by_node=group_by_node,
        )

    async def get_admin_usage_by_id(
        self, db: AsyncSession, admin_id: int, admin: AdminDetails, query: AdminUsageQuery
    ) -> UserUsageStatsList:
        db_admin = await self.get_validated_admin_by_id(db, admin_id)
        await self._ensure_owner_target_access(db_admin, admin)
        return await self._get_admin_usage(
            db,
            db_admin,
            admin,
            start=query.start,
            end=query.end,
            period=query.period,
            node_id=query.node_id,
            group_by_node=query.group_by_node,
        )

    async def bulk_remove_admins(
        self, db: AsyncSession, bulk_admins: BulkAdminSelection, admin: AdminDetails
    ) -> RemoveAdminsResponse:
        """Remove multiple admins by ID."""
        db_admins = await self._get_validated_bulk_admins(db, bulk_admins.ids, admin)
        if any(self._is_owner_admin(db_admin) for db_admin in db_admins):
            await self.raise_error(message="Owner cannot be deleted via this endpoint. Use the setup flow.", code=403)

        usernames = [a.username for a in db_admins]
        admin_ids = [a.id for a in db_admins]
        await remove_admins(db, admin_ids)

        for username in usernames:
            logger.info(f'Admin "{username}" deleted by admin "{admin.username}"')
            asyncio.create_task(notification.remove_admin(username, admin.username))

        return RemoveAdminsResponse(admins=usernames, count=len(db_admins))

    @staticmethod
    def _build_bulk_action_response(admins: list) -> BulkAdminsActionResponse:
        usernames = [a.username for a in admins]
        return BulkAdminsActionResponse(admins=usernames, count=len(usernames))

    async def _get_validated_bulk_admins(
        self, db: AsyncSession, ids: list[int] | set[int], current_admin: AdminDetails
    ) -> list[Admin]:
        if not ids:
            return []

        ids_list = list(ids)

        admins = await get_admins(db, AdminListQuery(ids=ids_list, limit=len(ids_list)))

        # Verify every requested ID was found (mirrors the 404 in get_validated_admin_by_id)
        found_ids = {a.id for a in admins}
        missing = set(ids_list) - found_ids
        if missing:
            await self.raise_error(message="Admin not found", code=404)

        for db_admin in admins:
            await self._ensure_owner_target_access(db_admin, current_admin)

        return admins

    async def bulk_set_admins_disabled(
        self, db: AsyncSession, bulk_admins: BulkAdminSelection, current_admin: AdminDetails, *, is_disabled: bool
    ) -> BulkAdminsActionResponse:
        """Enable or disable selected admins in bulk."""
        db_admins = await self._get_validated_bulk_admins(db, bulk_admins.ids, current_admin)
        target_status = AdminStatus.disabled if is_disabled else AdminStatus.active

        for db_admin in db_admins:
            if is_disabled and db_admin.username == current_admin.username:
                await self.raise_error(message="You're not allowed to disable your own account.", code=403)

        admins_to_update = [a for a in db_admins if a.status != target_status]
        old_sync_blocked = {a.id: await admin_users_sync_blocked(a) for a in admins_to_update}
        for db_admin in admins_to_update:
            db_admin.status = target_status
        await db.commit()

        for db_admin in admins_to_update:
            await sync_admin_users_for_block_transition(db, db_admin, old_sync_blocked[db_admin.id])
            modified_admin = build_admin_details(db_admin, include_loaded_metrics=True)
            asyncio.create_task(notification.modify_admin(modified_admin, current_admin.username))
            logger.info(
                f'Admin "{db_admin.username}" bulk {"disabled" if is_disabled else "enabled"} by admin "{current_admin.username}"'
            )

        return self._build_bulk_action_response(admins_to_update)

    async def bulk_reset_admins_usage(
        self, db: AsyncSession, bulk_admins: BulkAdminSelection, admin: AdminDetails
    ) -> BulkAdminsActionResponse:
        """Reset usage for selected admins by ID."""
        db_admins = await self._get_validated_bulk_admins(db, bulk_admins.ids, admin)
        for db_admin in db_admins:
            old_users_sync_blocked = await admin_users_sync_blocked(db_admin)
            db_admin = await reset_admin_usage(db, db_admin=db_admin)
            await sync_admin_users_for_block_transition(db, db_admin, old_users_sync_blocked)
            reseted_admin = build_admin_details(db_admin, include_loaded_metrics=True)
            asyncio.create_task(notification.admin_usage_reset(reseted_admin, admin.username))
            logger.info(f'Admin "{db_admin.username}" usage has been reset by admin "{admin.username}"')
        return self._build_bulk_action_response(db_admins)

    async def bulk_disable_all_active_users_for_admins(
        self, db: AsyncSession, bulk_admins: BulkAdminSelection, admin: AdminDetails
    ) -> BulkAdminsActionResponse:
        """Disable all active users under selected admins."""
        db_admins = await self._get_validated_bulk_admins(db, bulk_admins.ids, admin)
        for db_admin in db_admins:
            await self._disable_all_active_users_for_admin(db, db_admin, admin)
        return self._build_bulk_action_response(db_admins)

    async def bulk_activate_all_disabled_users_for_admins(
        self, db: AsyncSession, bulk_admins: BulkAdminSelection, admin: AdminDetails
    ) -> BulkAdminsActionResponse:
        """Activate all disabled users under selected admins."""
        db_admins = await self._get_validated_bulk_admins(db, bulk_admins.ids, admin)
        for db_admin in db_admins:
            await self._activate_all_disabled_users_for_admin(db, db_admin, admin)
        return self._build_bulk_action_response(db_admins)

    async def bulk_remove_all_users_for_admins(
        self, db: AsyncSession, bulk_admins: BulkAdminSelection, admin: AdminDetails
    ) -> BulkAdminsActionResponse:
        """Remove all users under selected admins."""
        db_admins = await self._get_validated_bulk_admins(db, bulk_admins.ids, admin)
        for db_admin in db_admins:
            await self._remove_all_users_for_admin(db, db_admin, admin)
        return self._build_bulk_action_response(db_admins)
