import asyncio

from app import notification
from app.core.hosts import host_manager
from app.db import AsyncSession
from app.db.crud.host import (
    create_host,
    get_host_by_id,
    get_hosts,
    modify_host,
    modify_hosts as crud_modify_hosts,
    remove_host,
    remove_hosts,
)
from app.db.models import ProxyHost
from app.models.admin import AdminDetails
from app.models.client_template import ClientTemplateType
from app.models.host import (
    BaseHost,
    BulkHostsActionResponse,
    BulkHostSelection,
    CreateHost,
    HostListQuery,
    RemoveHostsResponse,
)
from app.operation import BaseOperation
from app.utils.logger import get_logger

logger = get_logger("host-operation")


class HostOperation(BaseOperation):
    async def get_hosts(self, db: AsyncSession, query: HostListQuery) -> list[BaseHost]:
        return await get_hosts(db=db, query=query)

    async def validate_subscription_templates(self, db: AsyncSession, host: CreateHost) -> None:
        if not host.subscription_templates or host.subscription_templates.xray is None:
            return

        db_template = await self.get_validated_client_template(db, host.subscription_templates.xray)
        if db_template.template_type != ClientTemplateType.xray_subscription.value:
            await self.raise_error("Selected template must be an Xray subscription template", 400, db=db)

    @staticmethod
    def _download_host_id(host: BaseHost | ProxyHost) -> int | None:
        settings = host.transport_settings
        if isinstance(settings, dict):
            return (settings.get("xhttp_settings") or {}).get("download_settings")
        return settings.xhttp_settings.download_settings if settings and settings.xhttp_settings else None

    async def validate_ds_host(
        self,
        db: AsyncSession,
        host: BaseHost | ProxyHost,
        host_id: int | None = None,
        *,
        hosts_by_id: dict[int, ProxyHost | CreateHost] | None = None,
    ) -> None:
        if nested_host := self._download_host_id(host):
            if host_id and nested_host == host_id:
                await self.raise_error("download host cannot be the same as the host", 400, db=db)
            ds_host = hosts_by_id.get(nested_host) if hosts_by_id is not None else await get_host_by_id(db, nested_host)
            if not ds_host:
                await self.raise_error("download host not found", 404, db=db)
            if self._download_host_id(ds_host):
                await self.raise_error("download host cannot have a download host", 400, db=db)

    async def create_host(self, db: AsyncSession, new_host: CreateHost, admin: AdminDetails) -> BaseHost:
        await self.validate_subscription_templates(db, new_host)
        await self.validate_ds_host(db, new_host)

        await self.check_host_inbound_tags([new_host.inbound_tag])

        db_host = await create_host(db, new_host)

        logger.info(f'Host "{db_host.id}" added by admin "{admin.username}"')

        host = BaseHost.model_validate(db_host)
        asyncio.create_task(notification.create_host(host, admin.username))

        await host_manager.add_host(db, db_host)

        return host

    async def modify_host(
        self, db: AsyncSession, host_id: int, modified_host: CreateHost, admin: AdminDetails
    ) -> BaseHost:
        await self.validate_subscription_templates(db, modified_host)
        await self.validate_ds_host(db, modified_host, host_id)

        if modified_host.inbound_tag:
            await self.check_host_inbound_tags([modified_host.inbound_tag])

        db_host = await self.get_validated_host(db, host_id)

        db_host = await modify_host(db=db, db_host=db_host, modified_host=modified_host)

        logger.info(f'Host "{db_host.id}" modified by admin "{admin.username}"')

        host = BaseHost.model_validate(db_host)
        asyncio.create_task(notification.modify_host(host, admin.username))

        db_hosts = await get_hosts(db=db)
        dependents = [
            h
            for h in db_hosts
            if ((h.transport_settings or {}).get("xhttp_settings") or {}).get("download_settings") == host_id
        ]
        await host_manager.add_hosts(db, [db_host, *dependents])

        return host

    async def remove_host(self, db: AsyncSession, host_id: int, admin: AdminDetails):
        db_host = await self.get_validated_host(db, host_id)
        await remove_host(db, db_host)
        logger.info(f'Host "{db_host.id}" deleted by admin "{admin.username}"')

        host = BaseHost.model_validate(db_host)

        asyncio.create_task(notification.remove_host(host, admin.username))

        await host_manager.remove_host(host.id)

    async def modify_hosts(
        self, db: AsyncSession, modified_hosts: list[CreateHost], admin: AdminDetails
    ) -> list[BaseHost]:
        try:
            db_hosts = await get_hosts(db=db)
            hosts_by_id = {host.id: host for host in db_hosts}
            host_ids = [host.id for host in modified_hosts if host.id is not None]
            modified_ids = set(host_ids)
            if len(host_ids) != len(modified_ids):
                await self.raise_error("Duplicate host IDs", 400, db=db)
            final_hosts = hosts_by_id | {host.id: host for host in modified_hosts if host.id in hosts_by_id}
            for host in modified_hosts:
                await self.validate_subscription_templates(db, host)
                await self.validate_ds_host(db, host, host.id, hosts_by_id=final_hosts)
            # Updating a download host must not introduce a chain for an unchanged parent.
            for host in db_hosts:
                if host.id not in modified_ids and self._download_host_id(host) in modified_ids:
                    await self.validate_ds_host(db, host, host.id, hosts_by_id=final_hosts)
            await self.check_host_inbound_tags(list({host.inbound_tag for host in modified_hosts if host.inbound_tag}))
            await crud_modify_hosts(db, modified_hosts, db_hosts)
        except Exception:
            await db.rollback()
            raise

        db_hosts = await get_hosts(db=db)
        await host_manager.add_hosts(db, db_hosts)

        logger.info(f'Host\'s has been modified by admin "{admin.username}"')

        asyncio.create_task(notification.modify_hosts(admin.username))

        return db_hosts

    async def bulk_remove_hosts(
        self, db: AsyncSession, bulk_hosts: BulkHostSelection, admin: AdminDetails
    ) -> RemoveHostsResponse:
        """Remove multiple hosts by ID"""
        ids_list = list(bulk_hosts.ids)
        if not ids_list:
            await self.raise_error(message="Host selection cannot be empty", code=400)
        db_hosts = await get_hosts(db, HostListQuery(ids=ids_list, limit=len(ids_list)))

        found_ids = {h.id for h in db_hosts}
        missing = set(ids_list) - found_ids
        if missing:
            await self.raise_error(message="Host not found", code=404)

        host_ids = [h.id for h in db_hosts]

        # Batch delete using CRUD function
        await remove_hosts(db, host_ids)

        # Update host manager and notify
        for db_host in db_hosts:
            logger.info(f'Host "{db_host.id}" deleted by admin "{admin.username}"')
            host = BaseHost.model_validate(db_host)
            asyncio.create_task(notification.remove_host(host, admin.username))
            await host_manager.remove_host(host.id)

        return RemoveHostsResponse(hosts=[str(h.id) for h in db_hosts], count=len(db_hosts))

    @staticmethod
    def _build_bulk_action_response(hosts: list[ProxyHost]) -> BulkHostsActionResponse:
        host_ids = [str(host.id) for host in hosts if host.id is not None]
        return BulkHostsActionResponse(hosts=host_ids, count=len(host_ids))

    async def bulk_set_hosts_disabled(
        self,
        db: AsyncSession,
        bulk_hosts: BulkHostSelection,
        admin: AdminDetails,
        *,
        is_disabled: bool,
    ) -> BulkHostsActionResponse:
        """Change the enabled state of an explicitly selected, nonempty set of hosts."""
        ids_list = list(bulk_hosts.ids)
        if not ids_list:
            await self.raise_error(message="Host selection cannot be empty", code=400)
        db_hosts = await get_hosts(db, HostListQuery(ids=ids_list, limit=len(ids_list)))

        found_ids = {h.id for h in db_hosts}
        missing = set(ids_list) - found_ids
        if missing:
            await self.raise_error(message="Host not found", code=404)

        hosts_to_update = [db_host for db_host in db_hosts if db_host.is_disabled != is_disabled]

        for db_host in hosts_to_update:
            db_host.is_disabled = is_disabled

        await db.commit()

        for db_host in hosts_to_update:
            await db.refresh(db_host)

        if hosts_to_update:
            await host_manager.add_hosts(db, hosts_to_update)

        for db_host in hosts_to_update:
            host = BaseHost.model_validate(db_host)
            asyncio.create_task(notification.modify_host(host, admin.username))
            logger.info(
                f'Host "{db_host.id}" bulk {"disabled" if is_disabled else "enabled"} by admin "{admin.username}"'
            )

        return self._build_bulk_action_response(hosts_to_update)
