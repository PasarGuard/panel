from enum import Enum

from pydantic import BaseModel, Field

from app.db.models import NodeStatus
from app.models.validators import AwareDatetime


class WarpProfileStatus(str, Enum):
    pending = "pending"
    registering = "registering"
    ready = "ready"
    applied = "applied"
    error = "error"


class WarpNodeResponse(BaseModel):
    node_id: int
    name: str
    node_status: NodeStatus
    status: WarpProfileStatus
    registered_at: AwareDatetime | None = None
    applied_at: AwareDatetime | None = None
    last_error: str | None = None


class CoreWarpResponse(BaseModel):
    outbound_tag: str | None
    nodes: list[WarpNodeResponse]


class WarpRetryRequest(BaseModel):
    node_id: int | None = Field(default=None, gt=0)
