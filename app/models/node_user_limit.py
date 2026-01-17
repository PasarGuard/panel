from pydantic import BaseModel, ConfigDict, Field


class NodeUserLimitBase(BaseModel):
    """Base schema for node user limits"""

    user_id: int
    node_id: int
    data_limit: int = Field(ge=0, default=0, description="Per-user data limit for this node in bytes")
    data_limit_reset_strategy: str = Field(default="no_reset", description="Reset strategy for per-user limit")
    reset_time: int = Field(default=-1, description="Reset time for the limit")


class NodeUserLimitCreate(NodeUserLimitBase):
    """Schema for creating a new node user limit"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 1,
                "node_id": 1,
                "data_limit": 10737418240,  # 10 GB
            }
        }
    )


class NodeUserLimitModify(BaseModel):
    """Schema for modifying an existing node user limit"""

    data_limit: int = Field(ge=0, description="Per-user data limit for this node in bytes")
    data_limit_reset_strategy: str | None = Field(default=None, description="Reset strategy for per-user limit")
    reset_time: int | None = Field(default=None, description="Reset time for the limit")

    model_config = ConfigDict(json_schema_extra={"example": {"data_limit": 21474836480, "data_limit_reset_strategy": "month", "reset_time": 1}})  # 20 GB


class NodeUserLimitResponse(NodeUserLimitBase):
    """Schema for node user limit responses"""

    id: int

    model_config = ConfigDict(from_attributes=True)


class NodeUserLimitsResponse(BaseModel):
    """Schema for listing multiple node user limits"""

    limits: list[NodeUserLimitResponse]
    total: int


class BulkSetLimitRequest(BaseModel):
    """Schema for setting the same limit for all users on a node"""

    node_id: int
    data_limit: int = Field(ge=0, description="Data limit in bytes to apply to all users on this node")
    data_limit_reset_strategy: str = Field(default="no_reset", description="Reset strategy for per-user limits")
    reset_time: int = Field(default=-1, description="Reset time for the limits")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "node_id": 1,
                "data_limit": 10737418240,  # 10 GB
                "data_limit_reset_strategy": "month",
                "reset_time": 1,
            }
        }
    )
