from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .validators import ListValidator


class ClientTemplateType(StrEnum):
    clash_subscription = "clash_subscription"
    xray_subscription = "xray_subscription"
    singbox_subscription = "singbox_subscription"
    user_agent = "user_agent"
    grpc_user_agent = "grpc_user_agent"


class ClientTemplateBase(BaseModel):
    name: str = Field(max_length=64)
    template_type: ClientTemplateType
    content: str
    is_default: bool = Field(default=False)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name can't be empty")
        return stripped

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("content can't be empty")
        return value


class ClientTemplateCreate(ClientTemplateBase):
    pass


class ClientTemplateModify(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    content: str | None = None
    is_default: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("name can't be empty")
        return stripped

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("content can't be empty")
        return value


class ClientTemplateResponse(BaseModel):
    id: int
    name: str
    template_type: ClientTemplateType
    content: str
    is_default: bool
    is_system: bool

    model_config = ConfigDict(from_attributes=True)


class ClientTemplateResponseList(BaseModel):
    count: int
    templates: list[ClientTemplateResponse] = []

    model_config = ConfigDict(from_attributes=True)


class ClientTemplateSimple(BaseModel):
    id: int
    name: str
    template_type: ClientTemplateType
    is_default: bool

    model_config = ConfigDict(from_attributes=True)


class ClientTemplatesSimpleResponse(BaseModel):
    templates: list[ClientTemplateSimple]
    total: int


class BulkClientTemplateSelection(BaseModel):
    """Model for bulk client template selection by IDs"""

    ids: set[int] = Field(default_factory=set)

    @field_validator("ids", mode="after")
    @classmethod
    def ids_validator(cls, v):
        return ListValidator.not_null_list(list(v), "template")


class RemoveClientTemplatesResponse(BaseModel):
    """Response model for bulk client template deletion"""

    templates: list[str]
    count: int
