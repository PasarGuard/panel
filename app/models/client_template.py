from enum import Enum, StrEnum
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .validators import ListValidator


class ClientTemplateType(StrEnum):
    clash_subscription = "clash_subscription"
    xray_subscription = "xray_subscription"
    singbox_subscription = "singbox_subscription"
    user_agent = "user_agent"
    grpc_user_agent = "grpc_user_agent"


class TemplateSource(NamedTuple):
    """A stored client template as subscriptions render it. The id names it in failure reports."""

    content: str
    use_jinja: bool
    id: int


def effective_use_jinja(template_type: ClientTemplateType, use_jinja: bool) -> bool:
    """Clash always needs Jinja2: it renders `conf`, built once the proxies exist. User-Agent lists never get it."""
    if template_type in (ClientTemplateType.user_agent, ClientTemplateType.grpc_user_agent):
        return False
    return use_jinja or template_type == ClientTemplateType.clash_subscription


class ClientTemplateBase(BaseModel):
    name: str = Field(max_length=64)
    template_type: ClientTemplateType
    content: str
    is_default: bool = Field(default=False)
    # Forced on for clash_subscription (it renders `conf`, built once the proxies exist), off for the User-Agent lists.
    use_jinja: bool = Field(default=False)

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
    use_jinja: bool | None = None

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


class ClientTemplateValidate(BaseModel):
    template_type: ClientTemplateType
    content: str
    use_jinja: bool = Field(default=False)


class ClientTemplateValidation(BaseModel):
    valid: bool
    error: str | None = None
    # Line of `content` the error points at, when it can be told.
    line: int | None = None


class ClientTemplateResponse(BaseModel):
    id: int
    name: str
    template_type: ClientTemplateType
    content: str
    is_default: bool
    is_system: bool
    use_jinja: bool

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


class ClientTemplateSimpleSortField(str, Enum):
    id = "id"
    template_name = "name"
    template_type = "type"


class SortDirection(str, Enum):
    asc = "asc"
    desc = "desc"


class ClientTemplateSimpleSortOption(str, Enum):
    id = "id"
    template_name = "name"
    template_type = "type"
    desc_id = "-id"
    desc_template_name = "-name"
    desc_template_type = "-type"

    @property
    def field(self) -> ClientTemplateSimpleSortField:
        return ClientTemplateSimpleSortField(self.value.lstrip("-"))

    @property
    def direction(self) -> SortDirection:
        return SortDirection.desc if self.value.startswith("-") else SortDirection.asc


class ClientTemplateListQuery(BaseModel):
    ids: list[int] | None = None
    template_type: ClientTemplateType | None = None
    offset: int | None = None
    limit: int | None = None


class ClientTemplateSimpleListQuery(BaseModel):
    ids: list[int] | None = None
    template_type: ClientTemplateType | None = None
    offset: int | None = None
    limit: int | None = None
    search: str | None = None
    sort: list[ClientTemplateSimpleSortOption] = Field(default_factory=list)
    all: bool = False

    @field_validator("sort", mode="before")
    @classmethod
    def validate_sort(cls, value):
        return ListValidator.normalize_enum_list_input(value, ClientTemplateSimpleSortOption)


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
