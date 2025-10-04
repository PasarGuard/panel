import asyncio

from app import notification
from app.db import AsyncSession
from app.db.crud.bulk import add_groups_to_users, remove_groups_from_users
from app.db.crud.group import create_group, get_group, modify_group, remove_group
from app.db.crud.user import get_users
from app.db.models import Admin
from app.models.group import BulkGroup, Group, GroupCreate, GroupModify, GroupResponse, GroupsResponse
from app.models.user import BulkOperationResponse
from app.node import node_manager
from app.operation import BaseOperation, OperatorType
from app.utils.logger import get_logger

logger = get_logger("group-operation")


class GroupOperation(BaseOperation):
    async def create_group(self, db: AsyncSession, new_group: GroupCreate, admin: Admin) -> Group:
        await self.check_inbound_tags(new_group.inbound_tags)

        db_group = await create_group(db, new_group)

        group = GroupResponse.model_validate(db_group)

        asyncio.create_task(notification.create_group(group, admin.username))

        logger.info(f'Group "{group.name}" created by admin "{admin.username}"')
        return group

    async def get_all_groups(
        self,
        db: AsyncSession,
        offset: int | None = None,
        limit: int | None = None,
    ) -> GroupsResponse:
        db_groups, count = await get_group(db, offset, limit)
        return GroupsResponse(groups=db_groups, total=count)

    async def modify_group(self, db: AsyncSession, group_id: int, modified_group: GroupModify, admin: Admin) -> Group:
        db_group = await self.get_validated_group(db, group_id)
        if modified_group.inbound_tags:
            await self.check_inbound_tags(modified_group.inbound_tags)
        db_group = await modify_group(db, db_group, modified_group)

        users = await get_users(db, group_ids=[db_group.id])
        await node_manager.update_users(users)

        group = GroupResponse.model_validate(db_group)

        asyncio.create_task(notification.modify_group(group, admin.username))

        logger.info(f'Group "{group.name}" modified by admin "{admin.username}"')
        return group

    async def remove_group(self, db: AsyncSession, group_id: int, admin: Admin) -> None:
        db_group = await self.get_validated_group(db, group_id)

        users = await get_users(db, group_ids=[db_group.id])
        username_list = [user.username for user in users]

        await remove_group(db, db_group)
        users = await get_users(db, usernames=username_list)

        await node_manager.update_users(users)

        logger.info(f'Group "{db_group.name}" deleted by admin "{admin.username}"')

        asyncio.create_task(notification.remove_group(db_group.id, admin.username))

    async def bulk_add_groups(self, db: AsyncSession, bulk_model: BulkGroup) -> BulkOperationResponse | int:
        users, users_count = await add_groups_to_users(db, bulk_model)

        await node_manager.update_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return BulkOperationResponse(
                detail=f"operation has been successfully done on {users_count} users",
                affected_count=users_count,
            )
        return users_count

    async def bulk_remove_groups(self, db: AsyncSession, bulk_model: BulkGroup) -> BulkOperationResponse | int:
        await self.validate_all_groups(db, bulk_model)

        users, users_count = await remove_groups_from_users(db, bulk_model)

        await node_manager.update_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return BulkOperationResponse(
                detail=f"operation has been successfully done on {users_count} users",
                affected_count=users_count,
            )
        return users_count
