import asyncio
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import notification
from app.db import AsyncSession
from app.db.crud.bulk import _create_group_filter, add_groups_to_users, remove_groups_from_users
from app.db.crud.group import (
    create_group,
    get_group,
    get_groups_by_ids,
    get_groups_simple,
    modify_group,
    remove_group,
    GroupsSortingOptionsSimple,
)
from app.db.crud.user import get_users
from app.db.models import Admin, Group as DBGroup, User, UserStatus, users_groups_association
from app.models.group import (
    BulkGroup,
    Group,
    GroupCreate,
    GroupModify,
    GroupResponse,
    GroupsResponse,
    GroupSimple,
    GroupsSimpleResponse,
)
from app.node.sync import sync_users
from app.operation import BaseOperation, OperatorType
from app.utils.logger import get_logger
from app.wireguard import ensure_single_wireguard_interface_for_groups, ensure_single_wireguard_interface_for_tags

logger = get_logger("group-operation")


class GroupOperation(BaseOperation):
    async def _validate_group_inbound_tags(self, inbound_tags: list[str]) -> None:
        try:
            await ensure_single_wireguard_interface_for_tags(inbound_tags, context="group")
        except ValueError as exc:
            await self.raise_error(str(exc), 400)

    async def _get_group_members_with_groups(self, db: AsyncSession, group_id: int) -> list[User]:
        stmt = (
            select(User)
            .join(users_groups_association, User.id == users_groups_association.c.user_id)
            .where(users_groups_association.c.groups_id == group_id)
            .options(selectinload(User.groups).selectinload(DBGroup.inbounds))
        )
        return list((await db.execute(stmt)).unique().scalars().all())

    async def _validate_group_update_user_assignments(
        self,
        db: AsyncSession,
        db_group: DBGroup,
        modified_group: GroupModify,
    ) -> None:
        final_is_disabled = modified_group.is_disabled if modified_group.is_disabled is not None else db_group.is_disabled
        final_inbound_tags = modified_group.inbound_tags if modified_group.inbound_tags is not None else db_group.inbound_tags
        final_group = SimpleNamespace(
            is_disabled=final_is_disabled,
            inbounds=[SimpleNamespace(tag=tag) for tag in final_inbound_tags],
        )

        members = await self._get_group_members_with_groups(db, db_group.id)
        for member in members:
            effective_groups = [group for group in member.groups if group.id != db_group.id]
            effective_groups.append(final_group)
            try:
                await ensure_single_wireguard_interface_for_groups(effective_groups, context="user")
            except ValueError as exc:
                await self.raise_error(str(exc), 400)

    async def _validate_bulk_group_addition(self, db: AsyncSession, bulk_model: BulkGroup) -> None:
        groups_to_add = await get_groups_by_ids(db, list(bulk_model.group_ids), load_users=False, load_inbounds=True)
        groups_by_id = {group.id: group for group in groups_to_add}
        missing_group_ids = [group_id for group_id in bulk_model.group_ids if group_id not in groups_by_id]
        if missing_group_ids:
            await self.raise_error("Group not found", 404)

        final_filter = _create_group_filter(bulk_model)
        stmt = select(User).where(final_filter).options(selectinload(User.groups).selectinload(DBGroup.inbounds))
        target_users = list((await db.execute(stmt)).unique().scalars().all())

        for user in target_users:
            final_groups = list({group.id: group for group in [*user.groups, *groups_to_add]}.values())
            try:
                await ensure_single_wireguard_interface_for_groups(final_groups, context="user")
            except ValueError as exc:
                await self.raise_error(str(exc), 400)

    async def create_group(self, db: AsyncSession, new_group: GroupCreate, admin: Admin) -> Group:
        await self.check_inbound_tags(new_group.inbound_tags)
        await self._validate_group_inbound_tags(new_group.inbound_tags)

        db_group = await create_group(db, new_group)

        group = GroupResponse.model_validate(db_group)

        asyncio.create_task(notification.create_group(group, admin.username))

        logger.info(f'Group "{group.name}" created by admin "{admin.username}"')
        return group

    async def get_all_groups(
        self, db: AsyncSession, offset: int | None = None, limit: int | None = None
    ) -> GroupsResponse:
        db_groups, count = await get_group(db, offset, limit)
        return GroupsResponse(groups=db_groups, total=count)

    async def get_groups_simple(
        self,
        db: AsyncSession,
        offset: int | None = None,
        limit: int | None = None,
        search: str | None = None,
        sort: str | None = None,
        all: bool = False,
    ) -> GroupsSimpleResponse:
        """Get lightweight group list with only id and name"""
        sort_list = []
        if sort is not None:
            opts = sort.strip(",").split(",")
            for opt in opts:
                try:
                    enum_member = GroupsSortingOptionsSimple[opt]
                    sort_list.append(enum_member)
                except KeyError:
                    await self.raise_error(message=f'"{opt}" is not a valid sort option', code=400)

        # Call CRUD function
        rows, total = await get_groups_simple(
            db=db,
            offset=offset,
            limit=limit,
            search=search,
            sort=sort_list if sort_list else None,
            skip_pagination=all,
        )

        # Convert tuples to Pydantic models
        groups = [GroupSimple(id=row[0], name=row[1]) for row in rows]

        return GroupsSimpleResponse(groups=groups, total=total)

    async def modify_group(self, db: AsyncSession, group_id: int, modified_group: GroupModify, admin: Admin) -> Group:
        db_group = await self.get_validated_group(db, group_id)
        if modified_group.inbound_tags is not None:
            await self.check_inbound_tags(modified_group.inbound_tags)
            await self._validate_group_inbound_tags(modified_group.inbound_tags)
        if modified_group.inbound_tags is not None or modified_group.is_disabled is not None:
            await self._validate_group_update_user_assignments(db, db_group, modified_group)
        db_group = await modify_group(db, db_group, modified_group)

        users = await get_users(db, group_ids=[db_group.id], status=[UserStatus.active, UserStatus.on_hold])
        await sync_users(users)

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
        await sync_users(users)

        logger.info(f'Group "{db_group.name}" deleted by admin "{admin.username}"')

        asyncio.create_task(notification.remove_group(db_group.id, admin.username))

    async def bulk_add_groups(self, db: AsyncSession, bulk_model: BulkGroup):
        await self.validate_all_groups(db, bulk_model)
        await self._validate_bulk_group_addition(db, bulk_model)

        users, users_count = await add_groups_to_users(db, bulk_model)
        await sync_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return {"detail": f"operation has been successfuly done on {users_count} users"}
        return users_count

    async def bulk_remove_groups(self, db: AsyncSession, bulk_model: BulkGroup):
        await self.validate_all_groups(db, bulk_model)

        users, users_count = await remove_groups_from_users(db, bulk_model)
        await sync_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return {"detail": f"operation has been successfuly done on {users_count} users"}
        return users_count
