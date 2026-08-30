import asyncio

from app import notification
from app.db import AsyncSession, GetDB
from app.db.crud.bulk import add_groups_to_users, count_bulk_group_scope, remove_groups_from_users
from app.db.crud.group import (
    create_group,
    get_group,
    get_group_for_sync_update,
    get_group_user_count,
    get_group_user_ids_batch,
    get_groups_by_ids,
    get_groups_simple,
    load_group_attrs,
    modify_group,
    remove_group,
    remove_groups,
)
from app.db.crud.group_lock import lock_group_policy_writes
from app.db.crud.user import get_users, get_users_for_node_sync
from app.db.crud.wireguard import get_users_accessible_tags, sync_users_allocations
from app.db.models import Admin
from app.models.group import (
    BulkGroup,
    BulkGroupsActionResponse,
    BulkGroupSelection,
    Group,
    GroupCreate,
    GroupListQuery,
    GroupModify,
    GroupResponse,
    GroupSimple,
    GroupSimpleListQuery,
    GroupsResponse,
    GroupsSimpleResponse,
    RemoveGroupsResponse,
)
from app.models.user import BulkOperationDryRunResponse, UserListQuery
from app.node.sync import sync_users
from app.operation import BaseOperation, OperatorType
from app.operation.permissions import apply_group_access
from app.utils.logger import get_logger

logger = get_logger("group-operation")
GROUP_USER_SYNC_BATCH_SIZE = 1_000
_group_user_sync_tasks: dict[int, asyncio.Task] = {}


class GroupOperation(BaseOperation):
    async def _get_group_with_access(
        self,
        db: AsyncSession,
        group_id: int,
        admin: Admin,
        *,
        load_users: bool = True,
        load_inbounds: bool = True,
        coordinate_sync: bool = False,
    ) -> Group:
        """Fetch a group, returning 404 if it doesn't exist or is outside the admin's allowed set."""
        allowed = apply_group_access(admin, [group_id])
        # If allowed is an empty list, the id was filtered out → not accessible
        if allowed is not None and group_id not in allowed:
            await self.raise_error("Group not found", 404)
        if coordinate_sync:
            # Association writers follow policy-lock -> group-lock ordering;
            # inbound cleanup uses the same protocol during discovery.
            await lock_group_policy_writes(db)
            db_group = await get_group_for_sync_update(db, group_id)
            if db_group is None:
                await self.raise_error("Group not found", 404)
            return db_group
        db_group = await self.get_validated_group(
            db,
            group_id,
            load_users=load_users,
            load_inbounds=load_inbounds,
        )
        return db_group

    @staticmethod
    async def _build_group_response(db: AsyncSession, db_group: Group) -> GroupResponse:
        """Build a response without hydrating the group's users."""
        return GroupResponse(
            id=db_group.id,
            name=db_group.name,
            inbound_tags=db_group.inbound_tags,
            is_disabled=db_group.is_disabled,
            total_users=await get_group_user_count(db, db_group.id),
        )

    async def _sync_group_users(
        self,
        group_id: int,
        *,
        expected_inbound_tags: frozenset[str],
        expected_is_disabled: bool,
    ) -> None:
        """Reconcile group users in coordinated, keyset-paginated batches."""
        after_user_id = 0
        synced_users = 0

        while True:
            async with GetDB() as db:
                db_group = await get_group_for_sync_update(db, group_id)
                if db_group is None or (
                    frozenset(db_group.inbound_tags) != expected_inbound_tags
                    or db_group.is_disabled != expected_is_disabled
                ):
                    await db.rollback()
                    logger.info('Background sync superseded for group id "%s"', group_id)
                    return

                user_ids = await get_group_user_ids_batch(
                    db,
                    group_id,
                    after_user_id=after_user_id,
                    limit=GROUP_USER_SYNC_BATCH_SIZE,
                )
                if not user_ids:
                    await db.rollback()
                    break

                users = await get_users_for_node_sync(db, user_ids)
                inbound_tags_by_user = await get_users_accessible_tags(db, [user.id for user in users])
                await sync_users_allocations(db, users, tags_by_user=inbound_tags_by_user)
                await db.commit()

                # Persist allocations first, then reacquire the distributed
                # group lock and validate again. An update committed in this
                # small gap supersedes this batch before anything is sent.
                db_group = await get_group_for_sync_update(db, group_id)
                if db_group is None or (
                    frozenset(db_group.inbound_tags) != expected_inbound_tags
                    or db_group.is_disabled != expected_is_disabled
                ):
                    await db.rollback()
                    logger.info('Background sync superseded before dispatch for group id "%s"', group_id)
                    return

                await sync_users(
                    users,
                    inbound_tags_by_user=inbound_tags_by_user,
                    wait_for_dispatch=True,
                )
                await db.rollback()

                synced_users += len(users)
                after_user_id = user_ids[-1]

        logger.info('Background sync completed for group id "%s": %d users', group_id, synced_users)

    async def _sync_group_users_safely(
        self,
        group_id: int,
        *,
        expected_inbound_tags: frozenset[str],
        expected_is_disabled: bool,
    ) -> None:
        """Run a background group sync while logging recoverable failures."""
        try:
            await self._sync_group_users(
                group_id,
                expected_inbound_tags=expected_inbound_tags,
                expected_is_disabled=expected_is_disabled,
            )
        except Exception:
            logger.exception('Background sync failed for group id "%s"', group_id)

    def _schedule_group_user_sync(
        self,
        group_id: int,
        *,
        expected_inbound_tags: frozenset[str],
        expected_is_disabled: bool,
    ) -> None:
        """Schedule the latest local sync; database locking coordinates workers."""
        previous_task = _group_user_sync_tasks.get(group_id)
        if previous_task is not None and not previous_task.done():
            previous_task.cancel()

        task = asyncio.create_task(
            self._sync_group_users_safely(
                group_id,
                expected_inbound_tags=expected_inbound_tags,
                expected_is_disabled=expected_is_disabled,
            )
        )
        _group_user_sync_tasks[group_id] = task

        def remove_completed_task(completed_task: asyncio.Task) -> None:
            if _group_user_sync_tasks.get(group_id) is completed_task:
                _group_user_sync_tasks.pop(group_id, None)

        task.add_done_callback(remove_completed_task)

    async def _sync_users_allocations(self, db: AsyncSession, users) -> None:
        try:
            await sync_users_allocations(db, users)
        except ValueError as exc:  # WireGuard subnet exhausted
            await self.raise_error(message=str(exc), code=400, db=db)

    async def create_group(self, db: AsyncSession, new_group: GroupCreate, admin: Admin) -> Group:
        await self.check_inbound_tags(new_group.inbound_tags)
        await lock_group_policy_writes(db)
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

    async def modify_group(
        self,
        db: AsyncSession,
        group_id: int,
        modified_group: GroupModify,
        admin: Admin,
    ) -> GroupResponse:
        db_group = await self._get_group_with_access(
            db,
            group_id,
            admin,
            load_users=False,
            coordinate_sync=True,
        )
        inbound_tags_changed = modified_group.inbound_tags is not None and set(modified_group.inbound_tags) != set(
            db_group.inbound_tags
        )
        status_changed = modified_group.is_disabled is not None and modified_group.is_disabled != db_group.is_disabled

        if inbound_tags_changed:
            await self.check_inbound_tags(modified_group.inbound_tags)

        effective_modify = modified_group
        if modified_group.inbound_tags is not None and not inbound_tags_changed:
            # The dashboard sends the complete object. Avoid rewriting the
            # many-to-many relation when only the group name changed.
            effective_modify = modified_group.model_copy(update={"inbound_tags": None})

        db_group = await modify_group(db, db_group, effective_modify, load_users=False)
        group = await self._build_group_response(db, db_group)

        if inbound_tags_changed or status_changed:
            self._schedule_group_user_sync(
                db_group.id,
                expected_inbound_tags=frozenset(group.inbound_tags),
                expected_is_disabled=group.is_disabled,
            )

        asyncio.create_task(notification.modify_group(group, admin.username))

        logger.info(f'Group "{group.name}" modified by admin "{admin.username}"')
        return group

    async def remove_group(self, db: AsyncSession, group_id: int, admin: Admin) -> None:
        db_group = await self._get_group_with_access(db, group_id, admin)

        users = await get_users(db, query=UserListQuery(group_ids=[db_group.id]))
        username_list = [user.username for user in users]

        await remove_group(db, db_group)

        users = await get_users(db, query=UserListQuery(username=username_list), load_admin_role=True)
        await self._sync_users_allocations(db, users)
        await db.commit()
        await sync_users(users)

        logger.info(f'Group "{db_group.name}" deleted by admin "{admin.username}"')

        asyncio.create_task(notification.remove_group(db_group.id, admin.username))

    async def bulk_add_groups(self, db: AsyncSession, bulk_model: BulkGroup, admin: Admin):
        await self.validate_all_groups(db, bulk_model, admin)
        if bulk_model.dry_run:
            n = await count_bulk_group_scope(db, bulk_model)
            return BulkOperationDryRunResponse(affected_users=n)

        users, users_count = await add_groups_to_users(db, bulk_model)
        await self._sync_users_allocations(db, users)
        await db.commit()
        await sync_users(users)

        if self.operator_type in (OperatorType.API, OperatorType.WEB):
            return {"detail": f"operation has been successfuly done on {users_count} users"}
        return users_count

    async def bulk_remove_groups(self, db: AsyncSession, bulk_model: BulkGroup, admin: Admin):
        await self.validate_all_groups(db, bulk_model, admin)
        if bulk_model.dry_run:
            n = await count_bulk_group_scope(db, bulk_model)
            return BulkOperationDryRunResponse(affected_users=n)

        users, users_count = await remove_groups_from_users(db, bulk_model)
        await self._sync_users_allocations(db, users)
        await db.commit()
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
            await self._sync_users_allocations(db, users)
            await db.commit()
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
                query=UserListQuery(group_ids=[group.id for group in groups_to_update]),
                load_admin_role=True,
            )
            await self._sync_users_allocations(db, users)
            await db.commit()
            await sync_users(users)

        for db_group in groups_to_update:
            group = GroupResponse.model_validate(db_group)
            asyncio.create_task(notification.modify_group(group, admin.username))
            logger.info(
                f'Group "{db_group.name}" bulk {"disabled" if is_disabled else "enabled"} by admin "{admin.username}"'
            )

        return self._build_bulk_action_response(groups_to_update)
