from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CoreTemplateType(StrEnum):
    clash_subscription = "clash_subscription"
    xray_subscription = "xray_subscription"
    singbox_subscription = "singbox_subscription"
    user_agent = "user_agent"
    grpc_user_agent = "grpc_user_agent"


class CoreTemplateBase(BaseModel):
    name: str = Field(max_length=64)
    template_type: CoreTemplateType
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


class CoreTemplateCreate(CoreTemplateBase):
    pass


class CoreTemplateModify(BaseModel):
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


class CoreTemplateResponse(BaseModel):
    id: int
    name: str
    template_type: CoreTemplateType
    content: str
    is_default: bool
    is_system: bool

    model_config = ConfigDict(from_attributes=True)


class CoreTemplateResponseList(BaseModel):
    count: int
    templates: list[CoreTemplateResponse] = []

    model_config = ConfigDict(from_attributes=True)


class CoreTemplateSimple(BaseModel):
    id: int
    name: str
    template_type: CoreTemplateType
    is_default: bool

    model_config = ConfigDict(from_attributes=True)


class CoreTemplatesSimpleResponse(BaseModel):
    templates: list[CoreTemplateSimple]
    total: int
