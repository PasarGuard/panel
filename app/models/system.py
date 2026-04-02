from pydantic import BaseModel


class InboundSummary(BaseModel):
    tag: str
    protocol: str
    network: str | None = None
    wireguard_public_key: str | None = None
    wireguard_private_key: str | None = None
    wireguard_pre_shared_key: str | None = None
    wireguard_listen_port: int | None = None
    wireguard_addresses: list[str] | None = None
    wireguard_peer_keepalive_seconds: int | None = None


class SystemStats(BaseModel):
    version: str
    mem_total: int | None = None
    mem_used: int | None = None
    disk_total: int | None = None
    disk_used: int | None = None
    cpu_cores: int | None = None
    cpu_usage: float | None = None
    total_user: int
    online_users: int
    active_users: int
    on_hold_users: int
    disabled_users: int
    expired_users: int
    limited_users: int
    incoming_bandwidth: int
    outgoing_bandwidth: int


class WorkerHealth(BaseModel):
    status: str
    response_time_ms: int | None = None
    error: str | None = None


class WorkersHealth(BaseModel):
    scheduler: WorkerHealth
    node: WorkerHealth
