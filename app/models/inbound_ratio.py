from pydantic import BaseModel, Field


class InboundRatioResponse(BaseModel):
    """Panel-side inbound ratio settings: live inbound metadata plus the usage ratio."""

    tag: str
    protocol: str | None = None
    network: str | None = None
    security: str | None = None
    usage_coefficient: float = Field(default=1.0, ge=0)
    hosts_count: int = 0
    groups: list[str] = Field(default_factory=list)
    cores: list[str] = Field(default_factory=list)


class InboundRatioModify(BaseModel):
    usage_coefficient: float = Field(
        default=1.0,
        ge=0,
        description="Traffic multiplier for users whose groups expose this inbound. 1 = no change.",
        examples=[1.0, 2.0, 0.5],
    )
