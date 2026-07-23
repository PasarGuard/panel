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
from app.db.crud.user import get_users_by_ids
from app.db.crud.wireguard import (
    core_config_dict,
    get_wg_cores,
    reconcile_wireguard_subnets,
    wg_core_subnets,
)
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
    CoreType,
    RemoveCoresResponse,
)
from app.node.sync import sync_users
from app.models.reality_scan import RealityScanRequest, RealityScanResult
from app.operation import BaseOperation
from app.utils.logger import get_logger
from app.utils.reality_scan import RealityScanError, scan_reality_target

logger = get_logger("core-operation")


class CoreOperation(BaseOperation):
    async def _refresh_hosts_from_db(self, db: AsyncSession) -> None:
        db_hosts = await get_hosts(db=db)
        await host_manager.add_hosts(db, db_hosts)

    async def _validate_wireguard_subnet(self, db: AsyncSession, config: dict, *, exclude_core_id: int | None) -> None:
        """WG cores need at least one client subnet (v4 and/or v6). Overlapping subnets
        are rejected; identical CIDRs may be shared across cores (one allocation namespace)."""
        subnets = wg_core_subnets(config)
        if not subnets:
            await self.raise_error(message="WireGuard core needs an IPv4 or IPv6 interface address", code=400, db=db)
        for other in await get_wg_cores(db):
            if other.id == exclude_core_id:
                continue
            for subnet in subnets:
                for other_subnet in wg_core_subnets(core_config_dict(other)):
                    if other_subnet == subnet:
                        continue
                    if subnet.overlaps(other_subnet):
                        await self.raise_error(
                            message=(
                                f"WireGuard subnet {subnet} overlaps {other_subnet} "
                                f"of core '{other.name}' — use the identical CIDR or a disjoint subnet"
                            ),
                            code=400,
                            db=db,
                        )

    async def _reconcile_wireguard(self, db: AsyncSession) -> None:
        """Fix pool rows and user peer IPs after a WG core change, then resync changed users."""
        changed_ids = await reconcile_wireguard_subnets(db)
        await db.commit()
        if changed_ids:
            users = await get_users_by_ids(db, changed_ids, load_admin_role=True)
            await sync_users(users)

    async def scan_reality_target(self, request: RealityScanRequest) -> RealityScanResult:
        try:
            result = await scan_reality_target(target=request.target, timeout=request.timeout)
        except RealityScanError as e:
            await self.raise_error(message=str(e), code=400)
        except Exception as e:
            logger.warning("reality scan failed for %r: %s", request.target, e)
            await self.raise_error(message=f"Reality scan failed: {e}", code=502)
        return RealityScanResult.model_validate(result)

    async def create_core(self, db: AsyncSession, new_core: CoreCreate, admin: AdminDetails) -> CoreResponse:
        if new_core.type == CoreType.wg:
            await self._validate_wireguard_subnet(db, new_core.config, exclude_core_id=None)
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

        if new_core.type == CoreType.wg:
            await self._reconcile_wireguard(db)
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
        was_wg = db_core.type == CoreType.wg
        if modified_core.type == CoreType.wg:
            await self._validate_wireguard_subnet(db, modified_core.config, exclude_core_id=db_core.id)
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

        if was_wg or modified_core.type == CoreType.wg:
            await self._reconcile_wireguard(db)
        await self._refresh_hosts_from_db(db)

        return core

    async def delete_core(self, db: AsyncSession, core_id: int, admin: AdminDetails) -> None:
        if core_id == 1:
            return await self.raise_error(message="Cannot delete default core config", code=403)

        db_core = await self.get_validated_core_config(db, core_id)
        was_wg = db_core.type == CoreType.wg

        await remove_core_config(db, db_core)
        await core_manager.remove_core(db_core.id)

        asyncio.create_task(notification.remove_core(db_core.id, admin.username))

        logger.info(f'core config "{db_core.name}" deleted by admin "{admin.username}"')

        if was_wg:
            await self._reconcile_wireguard(db)
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
        any_wg = any(c.type == CoreType.wg for c in db_cores_list)

        # Batch delete using CRUD function
        await remove_cores(db, core_ids)

        # Remove from core manager and notify
        for core_id, core_name in zip(core_ids, core_names):
            await core_manager.remove_core(core_id)
            asyncio.create_task(notification.remove_core(core_id, admin.username))
            logger.info(f'core config "{core_name}" deleted by admin "{admin.username}"')

        if any_wg:
            await self._reconcile_wireguard(db)
        await self._refresh_hosts_from_db(db)

        return RemoveCoresResponse(cores=core_names, count=len(db_cores_list))
