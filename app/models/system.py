from pydantic import BaseModel


class SystemStats(BaseModel):
    version: str
    mem_total: int | None = None
    mem_used: int | None = None
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
