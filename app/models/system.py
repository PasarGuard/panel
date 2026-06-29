from pydantic import BaseModel


class InboundSummary(BaseModel):
    tag: str
    protocol: str
    network: str | None = None


class SystemResourceStats(BaseModel):
    version: str
    uptime_seconds: int
    mem_total: int | None = None
    mem_used: int | None = None
    disk_total: int | None = None
    disk_used: int | None = None
    cpu_cores: int | None = None
    cpu_usage: float | None = None


class SystemUsersStats(BaseModel):
    total_user: int
    online_users: int
    active_users: int
    on_hold_users: int
    disabled_users: int
    expired_users: int
    limited_users: int
    incoming_bandwidth: int
    outgoing_bandwidth: int


class SystemStats(SystemResourceStats, SystemUsersStats):
    pass


class WorkerHealth(BaseModel):
    status: str
    response_time_ms: int | None = None
    error: str | None = None


class WorkersHealth(BaseModel):
    scheduler: WorkerHealth
    node: WorkerHealth
