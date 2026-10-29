from pydantic import BaseModel, Field


class MyHostItem(BaseModel):
    host_id: int
    remark: str
    original_remark: str
    inbound_tag: str
    priority: int
    order: int
    is_disabled: bool


class MyHostUpdate(BaseModel):
    host_id: int
    remark: str | None = Field(default=None, max_length=256)
    is_disabled: bool = False


class MyHostsUpdate(BaseModel):
    hosts: list[MyHostUpdate]
