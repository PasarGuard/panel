import asyncio

from sqlalchemy.exc import IntegrityError

from app.db import AsyncSession
from app.db.models import ProxyHost
from app.models.admin import AdminDetails
from app.models.client_template import ClientTemplateType
from app.db.models import HostTag as DBHostTag
from app.models.host import (
    BaseHost,
    BulkHostSelection,
    BulkHostsActionResponse,
    CreateHost,
    HostListQuery,
    HostTag,
    HostTagCreate,
    HostTagModify,
    RemoveHostsResponse,
)
from app.operation import BaseOperation
from app.db.crud.host import (
    create_host,
    create_host_tag,
    get_host_by_id,
    get_host_tag_by_id,
    get_host_tag_by_name,
    get_host_tags,
    get_hosts,
    modify_host,
    modify_host_tag,
    remove_host,
    remove_host_tag,
    remove_hosts,
    resolve_host_tags,
)
from app.core.hosts import host_manager
from app.utils.logger import get_logger

from app import notification


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

    async def validate_host_tags(self, db: AsyncSession, tag_ids: list[int]) -> None:
        """Ensure every requested host-tag id actually exists."""
        unique_ids = list(dict.fromkeys(tag_ids or []))
        if not unique_ids:
            return
        resolved = await resolve_host_tags(db, unique_ids)
        if len(resolved) != len(unique_ids):
            found = {tag.id for tag in resolved}
            missing = [tag_id for tag_id in unique_ids if tag_id not in found]
            await self.raise_error(f"Host tag(s) not found: {missing}", 404, db=db)

    async def create_host(self, db: AsyncSession, new_host: CreateHost, admin: AdminDetails) -> BaseHost:
        await self.validate_subscription_templates(db, new_host)
        await self.validate_ds_host(db, new_host)

        await self.check_host_inbound_tags([new_host.inbound_tag])
        await self.validate_host_tags(db, new_host.tag_ids)

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
        await self.validate_host_tags(db, modified_host.tag_ids)

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

    async def get_validated_host_tag(self, db: AsyncSession, tag_id: int) -> DBHostTag:
        db_tag = await get_host_tag_by_id(db, tag_id)
        if not db_tag:
            await self.raise_error("Host tag not found", 404, db=db)
        return db_tag

    async def get_host_tags(self, db: AsyncSession) -> list[HostTag]:
        db_tags = await get_host_tags(db)
        return [HostTag.model_validate(tag) for tag in db_tags]

    async def create_host_tag(self, db: AsyncSession, new_tag: HostTagCreate, admin: AdminDetails) -> HostTag:
        if await get_host_tag_by_name(db, new_tag.name):
            await self.raise_error("A host tag with this name already exists", 409, db=db)
        try:
            db_tag = await create_host_tag(db, new_tag)
        except IntegrityError:
            await self.raise_error("A host tag with this name already exists", 409, db=db)
        logger.info(f'Host tag "{db_tag.name}" created by admin "{admin.username}"')
        return HostTag.model_validate(db_tag)

    async def modify_host_tag(
        self, db: AsyncSession, tag_id: int, modified_tag: HostTagModify, admin: AdminDetails
    ) -> HostTag:
        db_tag = await self.get_validated_host_tag(db, tag_id)
        if modified_tag.name and modified_tag.name != db_tag.name:
            existing = await get_host_tag_by_name(db, modified_tag.name)
            if existing and existing.id != db_tag.id:
                await self.raise_error("A host tag with this name already exists", 409, db=db)
        try:
            db_tag = await modify_host_tag(db, db_tag, modified_tag)
        except IntegrityError:
            await self.raise_error("A host tag with this name already exists", 409, db=db)
        logger.info(f'Host tag "{db_tag.name}" ({db_tag.id}) modified by admin "{admin.username}"')
        return HostTag.model_validate(db_tag)

    async def remove_host_tag(self, db: AsyncSession, tag_id: int, admin: AdminDetails) -> None:
        db_tag = await self.get_validated_host_tag(db, tag_id)
        name = db_tag.name
        await remove_host_tag(db, db_tag)
        logger.info(f'Host tag "{name}" ({tag_id}) deleted by admin "{admin.username}"')

    async def modify_hosts(
        self, db: AsyncSession, modified_hosts: list[CreateHost], admin: AdminDetails
    ) -> list[BaseHost]:
        for host in modified_hosts:
            await self.validate_subscription_templates(db, host)
            await self.validate_ds_host(db, host, host.id)

            old_host: ProxyHost | None = None
            if host.id is not None:
                old_host = await get_host_by_id(db, host.id)

            if old_host is None:
                await create_host(db, host)
            else:
                await modify_host(db, old_host, host)

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
        ids_list = list(bulk_hosts.ids)
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
            host = BaseHost.model_validate(db_host)
            asyncio.create_task(notification.modify_host(host, admin.username))
            await host_manager.add_host(db, db_host)
            logger.info(
                f'Host "{db_host.id}" bulk {"disabled" if is_disabled else "enabled"} by admin "{admin.username}"'
            )

        return self._build_bulk_action_response(hosts_to_update)
