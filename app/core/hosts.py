from sqlalchemy.ext.asyncio import AsyncSession

from app import on_startup
from app.core.manager import core_manager
from app.db import GetDB
from app.db.crud.host import get_host_by_id, get_hosts, get_or_create_inbound
from app.db.models import ProxyHost, ProxyHostSecurity
from app.models.host import MuxSettings, TransportSettings
from app.utils.store import DictStorage


def _prepare_host_data(host: ProxyHost) -> dict:
    return {
        "remark": host.remark,
        "inbound_tag": host.inbound_tag,
        "address": [v for v in host.address],
        "port": host.port,
        "path": host.path or None,
        "sni": [v for v in host.sni] if host.sni else [],
        "host": [v for v in host.host] if host.host else [],
        "alpn": [alpn.value for alpn in host.alpn] if host.alpn else [],
        "fingerprint": host.fingerprint.value,
        "tls": None if host.security == ProxyHostSecurity.inbound_default else host.security.value,
        "allowinsecure": host.allowinsecure,
        "fragment_settings": host.fragment_settings,
        "noise_settings": host.noise_settings,
        "random_user_agent": host.random_user_agent,
        "use_sni_as_host": host.use_sni_as_host,
        "http_headers": host.http_headers,
        "mux_settings": MuxSettings.model_validate(host.mux_settings).model_dump(by_alias=True, exclude_none=True)
        if host.mux_settings
        else {},
        "transport_settings": TransportSettings.model_validate(host.transport_settings).model_dump(
            by_alias=True, exclude_none=True
        )
        if host.transport_settings
        else {},
        "status": host.status,
        "ech_config_list": host.ech_config_list,
    }


@DictStorage
async def hosts(storage: dict, db: AsyncSession):
    inbounds_list = await core_manager.get_inbounds()
    for tag in inbounds_list:
        await get_or_create_inbound(db, tag)

    storage.clear()
    db_hosts = await get_hosts(db)

    for host in db_hosts:
        if host.is_disabled or (host.inbound_tag not in inbounds_list):
            continue
        downstream = None
        if (
            host.transport_settings
            and host.transport_settings.get("xhttp_settings")
            and (ds_host := host.transport_settings.get("xhttp_settings", {}).get("download_settings"))
        ):
            downstream = await get_host_by_id(db, ds_host)

        host_data = _prepare_host_data(host)

        if downstream:
            host_data["downloadSettings"] = _prepare_host_data(downstream)
        else:
            host_data["downloadSettings"] = None

        storage[host.id] = host_data


@on_startup
async def initialize_hosts():
    async with GetDB() as db:
        await hosts.update(db)
