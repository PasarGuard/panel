import asyncio

from app.db import AsyncSession
from app.db.models import ProxyHost
from app.models.client_template import ClientTemplateType
from app.models.host import CreateHost, BaseHost
from app.models.admin import AdminDetails
from app.operation import BaseOperation
from app.db.crud.host import (
    create_host,
    get_host_by_id,
    get_hosts,
    modify_host,
    remove_host,
)
from app.core.hosts import host_manager
from app.utils.logger import get_logger

from app import notification


logger = get_logger("host-operation")


class HostOperation(BaseOperation):
    async def validate_client_template_ids(self, db: AsyncSession, host: CreateHost) -> None:
        if not host.client_template_ids:
            return

        for template_type, template_id in host.client_template_ids.model_dump().items():
            if template_id is None:
                continue

            db_template = await self.get_validated_client_template(db, template_id)
            if db_template.template_type != template_type:
                await self.raise_error(
                    message=(
                        f'Client template "{template_id}" must be of type "{ClientTemplateType(template_type).value}"'
                    ),
                    code=400,
                    db=db,
                )

    async def get_hosts(self, db: AsyncSession, offset: int = 0, limit: int = 0) -> list[BaseHost]:
        return await get_hosts(db=db, offset=offset, limit=limit)

    async def validate_ds_host(self, db: AsyncSession, host: CreateHost, host_id: int | None = None) -> ProxyHost:
        if (
            host.transport_settings
            and host.transport_settings.xhttp_settings
            and (nested_host := host.transport_settings.xhttp_settings.download_settings)
        ):
            if host_id and nested_host == host_id:
                return await self.raise_error("download host cannot be the same as the host", 400, db=db)
            ds_host = await get_host_by_id(db, nested_host)
            if not ds_host:
                return await self.raise_error("download host not found", 404, db=db)
            if (
                ds_host.transport_settings
                and ds_host.transport_settings.get("xhttp_settings")
                and ds_host.transport_settings.get("xhttp_settings").get("download_settings")
            ):
                return await self.raise_error("download host cannot have a download host", 400, db=db)

    async def create_host(self, db: AsyncSession, new_host: CreateHost, admin: AdminDetails) -> BaseHost:
        await self.validate_ds_host(db, new_host)
        await self.validate_client_template_ids(db, new_host)

        await self.check_inbound_tags([new_host.inbound_tag])

        db_host = await create_host(db, new_host)

        logger.info(f'Host "{db_host.id}" added by admin "{admin.username}"')

        host = BaseHost.model_validate(db_host)
        asyncio.create_task(notification.create_host(host, admin.username))

        await host_manager.add_host(db, db_host)

        return host

    async def modify_host(
        self, db: AsyncSession, host_id: int, modified_host: CreateHost, admin: AdminDetails
    ) -> BaseHost:
        await self.validate_ds_host(db, modified_host, host_id)
        await self.validate_client_template_ids(db, modified_host)

        if modified_host.inbound_tag:
            await self.check_inbound_tags([modified_host.inbound_tag])

        db_host = await self.get_validated_host(db, host_id)

        db_host = await modify_host(db=db, db_host=db_host, modified_host=modified_host)

        logger.info(f'Host "{db_host.id}" modified by admin "{admin.username}"')

        host = BaseHost.model_validate(db_host)
        asyncio.create_task(notification.modify_host(host, admin.username))

        await host_manager.add_host(db, db_host)

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
        for host in modified_hosts:
            await self.validate_ds_host(db, host, host.id)
            await self.validate_client_template_ids(db, host)

            old_host: ProxyHost | None = None
            if host.id is not None:
                old_host = await get_host_by_id(db, host.id)

            if old_host is None:
                await create_host(db, host)
            else:
                await modify_host(db, old_host, host)

        await host_manager.add_hosts(db, modified_hosts)

        logger.info(f'Host\'s has been modified by admin "{admin.username}"')

        asyncio.create_task(notification.modify_hosts(admin.username))

        return await get_hosts(db=db)
