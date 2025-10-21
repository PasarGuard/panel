from asyncio import Lock
from copy import deepcopy

from aiocache import cached
from sqlalchemy.ext.asyncio import AsyncSession

from app import on_startup
from app.core.manager import core_manager
from app.db import GetDB
from app.db.crud.host import get_host_by_id, get_hosts, upsert_inbounds
from app.db.models import ProxyHostSecurity
from app.models.host import BaseHost
from app.models.subscription import (
    GRPCTransportConfig,
    KCPTransportConfig,
    QUICTransportConfig,
    SubscriptionInboundData,
    TCPTransportConfig,
    TLSConfig,
    WebSocketTransportConfig,
    XHTTPTransportConfig,
)


async def _prepare_subscription_inbound_data(
    host: BaseHost,
    down_settings: SubscriptionInboundData | None = None,
) -> SubscriptionInboundData:
    """
    Prepare host data - creates small config instances ONCE.
    Merges inbound config with host config.
    Random selection happens in share.py on every request!
    """
    # Get inbound configuration
    inbound_config = await core_manager.get_inbound_by_tag(host.inbound_tag)
    protocol = inbound_config["protocol"]

    ts = host.transport_settings
    network = inbound_config.get("network", "tcp")
    path = host.path or ""

    sni_list = list(host.sni) if host.sni else inbound_config.get("sni", [])
    host_list = list(host.host) if host.host else inbound_config.get("host", [])
    address_list = list(host.address) if host.address else []

    # Get Reality fields from inbound if applicable
    reality_pbk = inbound_config.get("pbk", "")
    reality_sid = inbound_config.get("sid", "")
    reality_sids = inbound_config.get("sids", [])
    reality_spx = inbound_config.get("spx") or ""  # Convert None to empty string

    # Merge TLS settings: host overrides inbound defaults
    tls_value = None if host.security == ProxyHostSecurity.inbound_default else host.security.value
    if tls_value is None:
        tls_value = inbound_config.get("tls")

    alpn_list = [alpn.value for alpn in host.alpn] if host.alpn else inbound_config.get("alpn", [])
    fp = host.fingerprint.value if host.fingerprint.value != "none" else inbound_config.get("fp", "")
    ais = host.allowinsecure if host.allowinsecure is not None else inbound_config.get("allowinsecure", False)

    # Create TLS config once with merged data
    tls_config = TLSConfig(
        tls=tls_value,
        sni=sni_list,
        fingerprint=fp,
        allowinsecure=ais,
        alpn_list=alpn_list,
        ech_config_list=host.ech_config_list,
        reality_public_key=reality_pbk,
        reality_short_id=reality_sid,
        reality_short_ids=reality_sids,
        reality_spx=reality_spx,
    )

    # Merge port: host overrides inbound (store as list for random selection)
    if host.port:
        # Host port is always an int
        port_list = [host.port]
    else:
        # Inbound port can be int or comma-separated string like "8080,8443,9090"
        inbound_port = inbound_config.get("port")
        if inbound_port:
            if isinstance(inbound_port, int):
                port_list = [inbound_port]
            elif isinstance(inbound_port, str):
                # Parse comma-separated string
                port_list = [int(p.strip()) for p in inbound_port.split(",") if p.strip()]
            else:
                port_list = []
        else:
            port_list = []

    # Get shadowsocks specific fields from inbound
    is_2022 = inbound_config.get("is_2022", False)
    ss_method = inbound_config.get("method", "")
    ss_password = inbound_config.get("password", "")

    # Get VLESS encryption from inbound
    encryption = inbound_config.get("encryption", "none")

    # Get flow from inbound (user can override later in share.py)
    inbound_flow = inbound_config.get("flow", "")
    if inbound_flow == "none":
        inbound_flow = ""

    # Network comes from inbound, NOT from checking which transport exists on host!
    # Host can have ALL transport configs, inbound determines which one is used

    # Create transport config based on network type from inbound
    # Always create the config, merge host settings with inbound defaults (host overrides inbound)
    if network in ("xhttp", "splithttp"):
        xs = ts.xhttp_settings if ts else None
        transport_config = XHTTPTransportConfig(
            path=path,
            host=host_list,
            mode=xs.mode.value if xs and xs.mode else "auto",
            no_grpc_header=xs.no_grpc_header if xs else None,
            sc_max_each_post_bytes=xs.sc_max_each_post_bytes if xs else None,
            sc_min_posts_interval_ms=xs.sc_min_posts_interval_ms if xs else None,
            x_padding_bytes=xs.x_padding_bytes if xs else None,
            xmux=xs.xmux.model_dump(by_alias=True, exclude_none=True) if xs and xs.xmux else None,
            download_settings=down_settings if xs and down_settings else None,
            http_headers=host.http_headers,
            random_user_agent=host.random_user_agent,
        )
    elif network in ("grpc", "gun"):
        gs = ts.grpc_settings if ts else None
        transport_config = GRPCTransportConfig(
            path=path,
            host=host_list,
            multi_mode=gs.multi_mode if gs else False,
            idle_timeout=gs.idle_timeout if gs else None,
            health_check_timeout=gs.health_check_timeout if gs else None,
            permit_without_stream=gs.permit_without_stream if gs else False,
            initial_windows_size=gs.initial_windows_size if gs else None,
            http_headers=host.http_headers,
            random_user_agent=host.random_user_agent,
        )
    elif network == "kcp":
        ks = ts.kcp_settings if ts else None
        transport_config = KCPTransportConfig(
            path=path,
            host=host_list,
            header_type=ks.header if ks else "none",
            mtu=ks.mtu if ks else None,
            tti=ks.tti if ks else None,
            uplink_capacity=ks.uplink_capacity if ks else None,
            downlink_capacity=ks.downlink_capacity if ks else None,
            congestion=ks.congestion if ks else False,
            read_buffer_size=ks.read_buffer_size if ks else None,
            write_buffer_size=ks.write_buffer_size if ks else None,
        )
    elif network == "quic":
        qs = ts.quic_settings if ts else None
        transport_config = QUICTransportConfig(
            path=path,
            host=host_list,
            header_type=qs.header if qs else "none",
        )
    elif network in ("ws", "websocket", "httpupgrade"):
        ws = ts.websocket_settings if ts else None
        transport_config = WebSocketTransportConfig(
            path=path,
            host=host_list,
            heartbeat_period=ws.heartbeatPeriod if ws else None,
            http_headers=host.http_headers,
            random_user_agent=host.random_user_agent,
        )
    elif network in ("tcp", "raw", "http", "h2"):
        # TCP/HTTP/H2 all use TCP transport
        tcps = ts.tcp_settings if ts else None
        transport_config = TCPTransportConfig(
            path=path,
            host=host_list,
            header_type=tcps.header if tcps else "none",
            request=tcps.request.model_dump(by_alias=True, exclude_none=True) if tcps and tcps.request else None,
            response=tcps.response.model_dump(by_alias=True, exclude_none=True) if tcps and tcps.response else None,
            http_headers=host.http_headers,
            random_user_agent=host.random_user_agent,
        )
    else:
        # Unknown network type, default to TCP
        transport_config = TCPTransportConfig(
            path=path,
            host=host_list,
            header_type="none",
            http_headers=host.http_headers,
            random_user_agent=host.random_user_agent,
        )

    return SubscriptionInboundData(
        remark=host.remark,
        inbound_tag=host.inbound_tag,
        protocol=protocol,
        address=address_list,
        port=port_list,  # Store the LIST for random selection!
        network=network,
        tls_config=tls_config,
        transport_config=transport_config,
        mux_settings=host.mux_settings.model_dump(by_alias=True, exclude_none=True) if host.mux_settings else None,
        is_2022=is_2022,
        method=ss_method,
        password=ss_password,
        encryption=encryption,
        inbound_flow=inbound_flow,
        random_user_agent=host.random_user_agent,
        use_sni_as_host=host.use_sni_as_host,
        fragment_settings=host.fragment_settings.model_dump() if host.fragment_settings else None,
        noise_settings=host.noise_settings.model_dump() if host.noise_settings else None,
        priority=host.priority,
        status=list(host.status) if host.status else None,
    )


class HostManager:
    def __init__(self):
        self._hosts = {}
        self._lock = Lock()

    async def setup(self, db: AsyncSession):
        db_hosts = await get_hosts(db)
        await self.add_hosts(db, db_hosts)

    async def _reset_cache(self):
        await self.get_hosts.cache.clear()

    @staticmethod
    async def _prepare_host_entry(
        db: AsyncSession, host: BaseHost, inbounds_list: list[str]
    ) -> tuple[int, dict] | None:
        if host.is_disabled or (host.inbound_tag not in inbounds_list):
            return None

        downstream_dict = None
        # Handle downstream for xhttp
        if (
            host.transport_settings
            and host.transport_settings.xhttp_settings
            and (ds_host := host.transport_settings.xhttp_settings.download_settings)
        ):
            downstream = await get_host_by_id(db, ds_host)
            downstream_data: SubscriptionInboundData = await _prepare_subscription_inbound_data(downstream)
            downstream_dict = downstream_data.model_dump(by_alias=True, exclude_none=True)

        subscription_data = await _prepare_subscription_inbound_data(host, downstream_dict)

        # Return subscription data directly
        return host.id, subscription_data

    async def add_host(self, db: AsyncSession, host: BaseHost):
        await self.add_hosts(db, [host])

    async def add_hosts(self, db: AsyncSession, hosts: list[BaseHost]):
        serialized_hosts = [BaseHost.model_validate(host) for host in hosts]
        inbounds_list = await core_manager.get_inbounds()
        await upsert_inbounds(db, inbounds_list)
        await db.commit()

        prepared_hosts = []
        hosts_to_remove = []
        for host in serialized_hosts:
            result = await self._prepare_host_entry(db, host, inbounds_list)
            if result:
                prepared_hosts.append(result)
            else:
                hosts_to_remove.append(host.id)

        # Acquire lock only for updating the dict and cache
        async with self._lock:
            for host_id, host_data in prepared_hosts:
                self._hosts[host_id] = host_data

            for host_id in hosts_to_remove:
                self._hosts.pop(host_id, None)

            await self._reset_cache()

    async def remove_host(self, id: int):
        async with self._lock:
            self._hosts.pop(id, None)
            await self._reset_cache()

    async def get_host(self, id: int) -> dict | None:
        async with self._lock:
            return deepcopy(self._hosts.get(id))

    @cached()
    async def get_hosts(self) -> dict[int, dict]:
        async with self._lock:
            # Return hosts sorted by priority (accessing from subscription_data)
            sorted_hosts = dict(sorted(self._hosts.items(), key=lambda x: x[1].priority))
            return deepcopy(sorted_hosts)


host_manager: HostManager = HostManager()


@on_startup
async def initialize_hosts():
    async with GetDB() as db:
        await host_manager.setup(db)
