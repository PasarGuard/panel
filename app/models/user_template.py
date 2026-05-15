import json
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import DataLimitResetStrategy, UserStatusCreate
from app.models.proxy import ShadowsocksMethods

from .validators import ListValidator, UserValidator


class ExtraSettings(BaseModel):
    method: ShadowsocksMethods | None = Field(ShadowsocksMethods.CHACHA20_POLY1305)

    def dict(self, *, no_obj=True, **kwargs):
        if no_obj:
            return json.loads(self.model_dump_json())
        return super().model_dump(**kwargs)


class UserTemplate(BaseModel):
    name: str | None = None
    data_limit: int | None = Field(ge=0, default=None, description="data_limit can be 0 or greater")
    hwid_limit: int | None = Field(default=None)
    expire_duration: int | None = Field(
        ge=0, default=None, description="expire_duration can be 0 or greater in seconds"
    )
    username_prefix: str | None = Field(max_length=20, default=None)
    username_suffix: str | None = Field(max_length=20, default=None)
    group_ids: list[int]
    extra_settings: ExtraSettings | None = None
    status: UserStatusCreate | None = None
    reset_usages: bool | None = None
    on_hold_timeout: int | None = None
    data_limit_reset_strategy: DataLimitResetStrategy = Field(default=DataLimitResetStrategy.no_reset)
    is_disabled: bool | None = None


class UserTemplateWithValidator(UserTemplate):
    @field_validator("status", mode="before", check_fields=False)
    def validate_status(cls, status, values):
        return UserValidator.validate_status(status, {UserStatusCreate.active, UserStatusCreate.on_hold}, values)

    @field_validator("username_prefix", "username_suffix", check_fields=False)
    @classmethod
    def validate_username(cls, v):
        return UserValidator.validate_username(v, False, True)


class UserTemplateCreate(UserTemplateWithValidator):
    @field_validator("group_ids", mode="after")
    @classmethod
    def group_ids_validator(cls, v):
        return ListValidator.not_null_list(v, "group")

    @field_validator("name", mode="after")
    @classmethod
    def name_validator(cls, v):
        if v:
            return v
        raise ValueError("name can't be empty")


class UserTemplateModify(UserTemplateWithValidator):
    group_ids: list[int] | None = None

    @field_validator("group_ids", mode="after")
    @classmethod
    def group_ids_validator(cls, v):
        return ListValidator.nullable_list(v, "group")

    @field_validator("name", mode="after")
    @classmethod
    def name_validator(cls, v):
        if v == "":
            raise ValueError("name can't be empty")
        return v


class UserTemplateResponse(UserTemplate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class UserTemplateSimple(BaseModel):
    """Lightweight user template model with only id and name for performance."""

    id: int
    name: str | None = None
    model_config = ConfigDict(from_attributes=True)


class UserTemplatesSimpleResponse(BaseModel):
    """Response model for lightweight user template list."""

    templates: list[UserTemplateSimple]
    total: int


class UserTemplateSimpleSortField(str, Enum):
    id = "id"
    template_name = "name"


class SortDirection(str, Enum):
    asc = "asc"
    desc = "desc"


class UserTemplateSimpleSortOption(str, Enum):
    id = "id"
    template_name = "name"
    desc_id = "-id"
    desc_template_name = "-name"

    @property
    def field(self) -> UserTemplateSimpleSortField:
        return UserTemplateSimpleSortField(self.value.lstrip("-"))

    @property
    def direction(self) -> SortDirection:
        return SortDirection.desc if self.value.startswith("-") else SortDirection.asc


class UserTemplateListQuery(BaseModel):
    ids: list[int] | None = None
    offset: int | None = None
    limit: int | None = None


class UserTemplateSimpleListQuery(BaseModel):
    ids: list[int] | None = None
    offset: int | None = None
    limit: int | None = None
    search: str | None = None
    sort: list[UserTemplateSimpleSortOption] = Field(default_factory=list)
    all: bool = False

    @field_validator("sort", mode="before")
    @classmethod
    def validate_sort(cls, value):
        return ListValidator.normalize_enum_list_input(value, UserTemplateSimpleSortOption)


class BulkUserTemplateSelection(BaseModel):
    """Model for bulk user template selection by IDs"""

    ids: set[int] = Field(default_factory=set)

    @field_validator("ids", mode="after")
    @classmethod
    def ids_validator(cls, v):
        return ListValidator.not_null_list(list(v), "template")


class RemoveUserTemplatesResponse(BaseModel):
    """Response model for bulk user template deletion"""

    templates: list[str]
    count: int


class BulkUserTemplatesActionResponse(BaseModel):
    """Response model for bulk user template actions."""

    templates: list[str]
    count: int
