import asyncio

from app import notification
from app.db import AsyncSession
from app.db.crud.bulk import add_groups_to_users, count_bulk_group_scope, remove_groups_from_users
from app.db.crud.group import (
    create_group,
    get_group,
    get_groups_by_ids,
    get_groups_simple,
    load_group_attrs,
    modify_group,
    remove_group,
    remove_groups,
)
from app.db.crud.user import get_users
from app.db.models import Admin, UserStatus
from app.models.group import (
    BulkGroupsActionResponse,
    BulkGroup,
    BulkGroupSelection,
    Group,
    GroupCreate,
    GroupListQuery,
    GroupModify,
    GroupResponse,
    GroupSimpleListQuery,
    GroupsResponse,
    GroupSimple,
    GroupsSimpleResponse,
    RemoveGroupsResponse,
)
from app.models.user import BulkOperationDryRunResponse, UserListQuery
from app.node.sync import sync_users
from app.operation import BaseOperation, OperatorType
from app.operation.permissions import apply_group_access
from app.utils.wireguard import bulk_reallocate_wireguard_peer_ips
from app.utils.logger import get_logger

logger = get_logger("group-operation")


class GroupOperation(BaseOperation):
    async def _get_group_with_access(self, db: AsyncSession, group_id: int, admin: Admin) -> Group:
        """Fetch a group, returning 404 if it doesn't exist or is outside the admin's allowed set."""
        allowed = apply_group_access(admin, [group_id])
        # If allowed is an empty list, the id was filtered out → not accessible
        if allowed is not None and group_id not in allowed:
            await self.raise_error("Group not found", 404)
        db_group = await self.get_validated_group(db, group_id)
        return db_group

    async def create_group(self, db: AsyncSession, new_group: GroupCreate, admin: Admin) -> Group:
        await self.check_inbound_tags(new_group.inbound_tags)
        db_group = await create_group(db, new_group)

        group = GroupResponse.model_validate(db_group)

        asyncio.create_task(notification.create_group(group, admin.username))

        logger.info(f'Group "{group.name}" created by admin "{admin.username}"')
        return group

    async def get_all_groups(self, db: AsyncSession, query: GroupListQuery, admin: Admin) -> GroupsResponse:
        query.ids = apply_group_access(admin, query.ids)
        db_groups, count = await get_group(db, query)
        return GroupsResponse(groups=db_groups, total=count)

    async def get_groups_simple(
        self,
        db: AsyncSession,
        query: GroupSimpleListQuery,
        admin: Admin,
    ) -> GroupsSimpleResponse:
        """Get lightweight group list with only id and name"""
        query.ids = apply_group_access(admin, query.ids)
        rows, total = await get_groups_simple(db=db, query=query)
        groups = [GroupSimple(id=row[0], name=row[1]) for row in rows]
        return GroupsSimpleResponse(groups=groups, total=total)

    async def modify_group(self, db: AsyncSession, group_id: int, modified_group: GroupModify, admin: Admin) -> Group:
        db_group = await self._get_group_with_access(db, group_id, admin)
        if modified_group.inbound_tags is not None:
            await self.check_inbound_tags(modified_group.inbound_tags)
        db_group = await modify_group(db, db_group, modified_group)

        users = await get_users(
            db,
            query=UserListQuery(group_ids=[db_group.id], status=[UserStatus.active, UserStatus.on_hold]),
            load_admin_role=True,
        )
        await bulk_reallocate_wireguard_peer_ips(db, users, dry_run=False, replace_all=False)
        await sync_users(users)

        group = GroupResponse.model_validate(db_group)

        asyncio.create_task(notification.modify_group(group, admin.username))

        logger.info(f'Group "{group.name}" modified by admin "{admin.username}"')
        return group

    async def remove_group(self, db: AsyncSession, group_id: int, admin: Admin) -> None:
        db_group = await self._get_group_with_access(db, group_id, admin)

        users = await get_users(db, query=UserListQuery(group_ids=[db_group.id]))
        username_list = [user.username for user in users]

        await remove_group(db, db_group)

        users = await get_users(db, query=UserListQuery(username=username_list), load_admin_role=True)
        await sync_users(users)

        logger.info(f'Group "{db_group.name}" deleted by admin "{admin.username}"')

        asyncio.create_task(notification.remove_group(db_group.id, admin.username))

    async def bulk_add_groups(self, db: AsyncSession, bulk_model: BulkGroup):
        await self.validate_all_groups(db, bulk_model)
        if bulk_model.dry_run:
            n = await count_bulk_group_scope(db, bulk_model)
            return BulkOperationDryRunResponse(affected_users=n)

        users, users_count = await add_groups_to_users(db, bulk_model)
        await bulk_reallocate_wireguard_peer_ips(db, users, dry_run=False, replace_all=False)
        await sync_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return {"detail": f"operation has been successfuly done on {users_count} users"}
        return users_count

    async def bulk_remove_groups(self, db: AsyncSession, bulk_model: BulkGroup):
        await self.validate_all_groups(db, bulk_model)
        if bulk_model.dry_run:
            n = await count_bulk_group_scope(db, bulk_model)
            return BulkOperationDryRunResponse(affected_users=n)

        users, users_count = await remove_groups_from_users(db, bulk_model)
        await sync_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return {"detail": f"operation has been successfuly done on {users_count} users"}
        return users_count

    async def bulk_remove_groups_by_id(
        self, db: AsyncSession, bulk_groups: BulkGroupSelection, admin: Admin
    ) -> RemoveGroupsResponse:
        """Remove multiple groups by ID"""
        requested_ids = list(bulk_groups.ids)
        allowed_ids = apply_group_access(admin, requested_ids)
        # Fetch all allowed groups in one query
        db_groups = await get_groups_by_ids(db, allowed_ids or [], load_users=False, load_inbounds=False)
        # Verify all requested ids were found and accessible
        found_ids = {g.id for g in db_groups}
        for gid in requested_ids:
            if gid not in found_ids:
                await self.raise_error("Group not found", 404)

        all_affected_usernames = set()
        for db_group in db_groups:
            users = await get_users(db, query=UserListQuery(group_ids=[db_group.id]))
            all_affected_usernames.update(user.username for user in users)

        group_ids = [g.id for g in db_groups]
        group_names = [g.name for g in db_groups]

        await remove_groups(db, group_ids)

        if all_affected_usernames:
            users = await get_users(
                db, query=UserListQuery(username=list(all_affected_usernames)), load_admin_role=True
            )
            await sync_users(users)

        for name, group_id in zip(group_names, group_ids):
            logger.info(f'Group "{name}" deleted by admin "{admin.username}"')
            asyncio.create_task(notification.remove_group(group_id, admin.username))

        return RemoveGroupsResponse(groups=group_names, count=len(db_groups))

    @staticmethod
    def _build_bulk_action_response(groups: list[Group]) -> BulkGroupsActionResponse:
        names = [group.name for group in groups]
        return BulkGroupsActionResponse(groups=names, count=len(names))

    async def bulk_set_groups_disabled(
        self,
        db: AsyncSession,
        bulk_groups: BulkGroupSelection,
        admin: Admin,
        *,
        is_disabled: bool,
    ) -> BulkGroupsActionResponse:
        requested_ids = list(bulk_groups.ids)
        allowed_ids = apply_group_access(admin, requested_ids)
        db_groups = await get_groups_by_ids(db, allowed_ids or [], load_users=False, load_inbounds=False)
        found_ids = {g.id for g in db_groups}
        for gid in requested_ids:
            if gid not in found_ids:
                await self.raise_error("Group not found", 404)

        groups_to_update = [db_group for db_group in db_groups if db_group.is_disabled != is_disabled]

        for db_group in groups_to_update:
            db_group.is_disabled = is_disabled

        await db.commit()

        for db_group in groups_to_update:
            await db.refresh(db_group)
            await load_group_attrs(db_group)

        if groups_to_update:
            users = await get_users(
                db,
                query=UserListQuery(
                    group_ids=[group.id for group in groups_to_update],
                    status=[UserStatus.active, UserStatus.on_hold],
                ),
                load_admin_role=True,
            )
            await sync_users(users)

        for db_group in groups_to_update:
            group = GroupResponse.model_validate(db_group)
            asyncio.create_task(notification.modify_group(group, admin.username))
            logger.info(
                f'Group "{db_group.name}" bulk {"disabled" if is_disabled else "enabled"} by admin "{admin.username}"'
            )

        return self._build_bulk_action_response(groups_to_update)
