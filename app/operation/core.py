import asyncio

from app import notification
from app.core.hosts import host_manager
from app.core.manager import core_manager
from app.db import AsyncSession
from app.db.crud.core import (
    create_core_config,
    get_core_configs,
    get_cores_simple,
    modify_core_config,
    remove_core_config,
    remove_cores,
)
from app.db.crud.host import get_hosts
from app.models.admin import AdminDetails
from app.models.core import (
    BulkCoreSelection,
    CoreCreate,
    CoreListQuery,
    CoreResponse,
    CoreResponseList,
    CoreSimpleListQuery,
    CoreSimple,
    CoresSimpleResponse,
    RemoveCoresResponse,
)
from app.operation import BaseOperation
from app.utils.logger import get_logger

logger = get_logger("core-operation")


class CoreOperation(BaseOperation):
    async def _refresh_hosts_from_db(self, db: AsyncSession) -> None:
        db_hosts = await get_hosts(db=db)
        await host_manager.add_hosts(db, db_hosts)

    async def create_core(self, db: AsyncSession, new_core: CoreCreate, admin: AdminDetails) -> CoreResponse:
        try:
            validated_core = core_manager.validate_core(
                new_core.config,
                new_core.exclude_inbound_tags,
                new_core.fallbacks_inbound_tags,
                new_core.type,
            )
            db_core = await create_core_config(db, new_core)
        except Exception as e:
            await self.raise_error(message=e, code=400, db=db)

        await core_manager.update_core(db_core, validated_core)
        logger.info(f'Core config "{db_core.id}" created by admin "{admin.username}"')

        core = CoreResponse.model_validate(db_core)
        asyncio.create_task(notification.create_core(core, admin.username))

        await self._refresh_hosts_from_db(db)

        return core

    async def get_all_cores(self, db: AsyncSession, query: CoreListQuery) -> CoreResponseList:
        db_cores, count = await get_core_configs(db, query)
        return CoreResponseList(cores=db_cores, count=count)

    async def get_cores_simple(self, db: AsyncSession, query: CoreSimpleListQuery) -> CoresSimpleResponse:
        """Get lightweight core list with only id and name"""
        rows, total = await get_cores_simple(db=db, query=query)

        cores = [CoreSimple(id=row[0], name=row[1], type=row[2]) for row in rows]

        return CoresSimpleResponse(cores=cores, total=total)

    async def modify_core(
        self, db: AsyncSession, core_id: int, modified_core: CoreCreate, admin: AdminDetails
    ) -> CoreResponse:
        db_core = await self.get_validated_core_config(db, core_id)
        try:
            validated_core = core_manager.validate_core(
                modified_core.config,
                modified_core.exclude_inbound_tags,
                modified_core.fallbacks_inbound_tags,
                modified_core.type,
            )
            db_core = await modify_core_config(db, db_core, modified_core)
        except Exception as e:
            await self.raise_error(message=e, code=400, db=db)

        await core_manager.update_core(db_core, validated_core)

        logger.info(f'Core config "{db_core.name}" modified by admin "{admin.username}"')

        core = CoreResponse.model_validate(db_core)
        asyncio.create_task(notification.modify_core(core, admin.username))

        await self._refresh_hosts_from_db(db)

        return core

    async def delete_core(self, db: AsyncSession, core_id: int, admin: AdminDetails) -> None:
        if core_id == 1:
            return await self.raise_error(message="Cannot delete default core config", code=403)

        db_core = await self.get_validated_core_config(db, core_id)

        await remove_core_config(db, db_core)
        await core_manager.remove_core(db_core.id)

        asyncio.create_task(notification.remove_core(db_core.id, admin.username))

        logger.info(f'core config "{db_core.name}" deleted by admin "{admin.username}"')

        await self._refresh_hosts_from_db(db)

    async def bulk_remove_cores(
        self, db: AsyncSession, bulk_cores: BulkCoreSelection, admin: AdminDetails
    ) -> RemoveCoresResponse:
        """Remove multiple cores by ID"""
        ids_list = list(bulk_cores.ids)
        db_cores_list, _ = await get_core_configs(db, CoreListQuery(ids=ids_list, limit=len(ids_list)))

        found_ids = {c.id for c in db_cores_list}
        missing = set(ids_list) - found_ids
        if missing:
            await self.raise_error(message="Core not found", code=404)

        for db_core in db_cores_list:
            if db_core.id == 1:
                await self.raise_error(message="Cannot delete default core config", code=403)

        core_ids = [c.id for c in db_cores_list]
        core_names = [c.name for c in db_cores_list]

        # Batch delete using CRUD function
        await remove_cores(db, core_ids)

        # Remove from core manager and notify
        for core_id, core_name in zip(core_ids, core_names):
            await core_manager.remove_core(core_id)
            asyncio.create_task(notification.remove_core(core_id, admin.username))
            logger.info(f'core config "{core_name}" deleted by admin "{admin.username}"')

        await self._refresh_hosts_from_db(db)

        return RemoveCoresResponse(cores=core_names, count=len(db_cores_list))
