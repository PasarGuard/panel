import asyncio

from app import notification
from app.core.hosts import host_manager
from app.core.manager import core_manager
from app.db import AsyncSession
from app.db.crud.core import (
    CoreSortingOptionsSimple,
    create_core_config,
    get_core_configs,
    get_cores_simple,
    modify_core_config,
    remove_core_config,
)
from app.db.crud.user import get_users_by_inbound_tags
from app.models.admin import AdminDetails
from app.models.core import CoreCreate, CoreResponse, CoreResponseList, CoreSimple, CoresSimpleResponse
from app.node.sync import sync_users
from app.operation import BaseOperation
from app.utils.logger import get_logger
from app.utils.wireguard import reconcile_wireguard_peer_ips_for_users

logger = get_logger("core-operation")


class CoreOperation(BaseOperation):
    @staticmethod
    def _core_inbound_tags(db_core) -> list[str]:
        return list(
            core_manager.validate_core(
                db_core.config,
                db_core.exclude_inbound_tags,
                db_core.fallbacks_inbound_tags,
                db_core.type,
            ).inbounds
        )

    async def create_core(self, db: AsyncSession, new_core: CoreCreate, admin: AdminDetails) -> CoreResponse:
        try:
            core_manager.validate_core(
                new_core.config,
                new_core.exclude_inbound_tags,
                new_core.fallbacks_inbound_tags,
                new_core.type,
            )
            db_core = await create_core_config(db, new_core)
        except Exception as e:
            await self.raise_error(message=e, code=400, db=db)

        await core_manager.update_core(db_core)
        logger.info(f'Core config "{db_core.id}" created by admin "{admin.username}"')

        core = CoreResponse.model_validate(db_core)
        asyncio.create_task(notification.create_core(core, admin.username))

        await host_manager.setup_local(db)

        return core

    async def get_all_cores(self, db: AsyncSession, offset: int, limit: int) -> CoreResponseList:
        db_cores, count = await get_core_configs(db, offset, limit)
        return CoreResponseList(cores=db_cores, count=count)

    async def get_cores_simple(
        self,
        db: AsyncSession,
        offset: int | None = None,
        limit: int | None = None,
        search: str | None = None,
        sort: str | None = None,
        all: bool = False,
    ) -> CoresSimpleResponse:
        """Get lightweight core list with only id and name"""
        sort_list = []
        if sort is not None:
            opts = sort.strip(",").split(",")
            for opt in opts:
                try:
                    enum_member = CoreSortingOptionsSimple[opt]
                    sort_list.append(enum_member)
                except KeyError:
                    await self.raise_error(message=f'"{opt}" is not a valid sort option', code=400)

        rows, total = await get_cores_simple(
            db=db,
            offset=offset,
            limit=limit,
            search=search,
            sort=sort_list if sort_list else None,
            skip_pagination=all,
        )

        cores = [CoreSimple(id=row[0], name=row[1], type=row[2]) for row in rows]

        return CoresSimpleResponse(cores=cores, total=total)

    async def modify_core(
        self, db: AsyncSession, core_id: int, modified_core: CoreCreate, admin: AdminDetails
    ) -> CoreResponse:
        db_core = await self.get_validated_core_config(db, core_id)
        old_inbound_tags = self._core_inbound_tags(db_core)
        try:
            core_manager.validate_core(
                modified_core.config,
                modified_core.exclude_inbound_tags,
                modified_core.fallbacks_inbound_tags,
                modified_core.type,
            )
            db_core = await modify_core_config(db, db_core, modified_core)
        except Exception as e:
            await self.raise_error(message=e, code=400, db=db)

        await core_manager.update_core(db_core)
        affected_users = await get_users_by_inbound_tags(
            db,
            list(dict.fromkeys([*old_inbound_tags, *self._core_inbound_tags(db_core)])),
        )
        await reconcile_wireguard_peer_ips_for_users(db, affected_users)
        await sync_users(affected_users)

        logger.info(f'Core config "{db_core.name}" modified by admin "{admin.username}"')

        core = CoreResponse.model_validate(db_core)
        asyncio.create_task(notification.modify_core(core, admin.username))

        await host_manager.setup_local(db)

        return core

    async def delete_core(self, db: AsyncSession, core_id: int, admin: AdminDetails) -> None:
        if core_id == 1:
            return await self.raise_error(message="Cannot delete default core config", code=403)

        db_core = await self.get_validated_core_config(db, core_id)
        affected_inbound_tags = self._core_inbound_tags(db_core)

        await remove_core_config(db, db_core)
        await core_manager.remove_core(db_core.id)
        affected_users = await get_users_by_inbound_tags(db, affected_inbound_tags)
        await reconcile_wireguard_peer_ips_for_users(db, affected_users)
        await sync_users(affected_users)

        asyncio.create_task(notification.remove_core(db_core.id, admin.username))

        logger.info(f'core config "{db_core.name}" deleted by admin "{admin.username}"')

        await host_manager.setup_local(db)
