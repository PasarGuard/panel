from datetime import datetime as dt
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import CoreType
from app.utils.helpers import fix_datetime_timezone

from .validators import ListValidator, StringArrayValidator


class CoreBase(BaseModel):
    name: str
    config: dict
    type: CoreType | None = Field(default=None)
    exclude_inbound_tags: set[str]
    fallbacks_inbound_tags: set[str]

    @property
    def exclude_tags(self) -> str:
        if self.exclude_inbound_tags:
            return ",".join(self.exclude_inbound_tags)
        return ""

    @property
    def fallback_tags(self) -> str:
        if self.fallbacks_inbound_tags:
            return ",".join(self.fallbacks_inbound_tags)
        return ""


class CoreCreate(CoreBase):
    name: str | None = Field(max_length=256, default=None)
    type: CoreType | None = Field(default=None)
    exclude_inbound_tags: set | None = Field(default=None)
    fallbacks_inbound_tags: set | None = Field(default=None)

    @field_validator("config", mode="before")
    def validate_config(cls, v: dict) -> dict:
        if not v:
            raise ValueError("config dictionary cannot be empty")
        return v

    @field_validator("exclude_inbound_tags", "fallbacks_inbound_tags", mode="after")
    def validate_sets(cls, v: set):
        return StringArrayValidator.len_check(v, 2048)


class CoreResponse(CoreBase):
    id: int
    created_at: dt

    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", mode="before")
    @classmethod
    def validator_date(cls, v):
        if not v:
            return v
        return fix_datetime_timezone(v)


class CoreResponseList(BaseModel):
    count: int
    cores: list[CoreResponse] = []

    model_config = ConfigDict(from_attributes=True)


class CoreSimple(BaseModel):
    """Lightweight core model with only id, name and type for performance."""

    id: int
    name: str
    type: CoreType | None = None
    model_config = ConfigDict(from_attributes=True)


class CoresSimpleResponse(BaseModel):
    """Response model for lightweight core list."""

    cores: list[CoreSimple]
    total: int


class CoreSimpleSortField(str, Enum):
    id = "id"
    core_name = "name"
    created_at = "created_at"


class SortDirection(str, Enum):
    asc = "asc"
    desc = "desc"


class CoreSimpleSortOption(str, Enum):
    id = "id"
    core_name = "name"
    created_at = "created_at"
    desc_id = "-id"
    desc_core_name = "-name"
    desc_created_at = "-created_at"

    @property
    def field(self) -> CoreSimpleSortField:
        return CoreSimpleSortField(self.value.lstrip("-"))

    @property
    def direction(self) -> SortDirection:
        return SortDirection.desc if self.value.startswith("-") else SortDirection.asc


class CoreListQuery(BaseModel):
    ids: list[int] | None = None
    offset: int | None = None
    limit: int | None = None


class CoreSimpleListQuery(BaseModel):
    ids: list[int] | None = None
    offset: int | None = None
    limit: int | None = None
    search: str | None = None
    sort: list[CoreSimpleSortOption] = Field(default_factory=list)
    all: bool = False

    @field_validator("sort", mode="before")
    @classmethod
    def validate_sort(cls, value):
        return ListValidator.normalize_enum_list_input(value, CoreSimpleSortOption)


class BulkCoreSelection(BaseModel):
    """Model for bulk core selection by IDs"""

    ids: set[int] = Field(default_factory=set)

    @field_validator("ids", mode="after")
    @classmethod
    def ids_validator(cls, v):
        return ListValidator.not_null_list(list(v), "core")


class RemoveCoresResponse(BaseModel):
    """Response model for bulk core deletion"""

    cores: list[str]
    count: int
