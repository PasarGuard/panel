from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .validators import ListValidator


class Group(BaseModel):
    name: str = Field(min_length=3, max_length=64)
    inbound_tags: list[str] | None = []
    is_disabled: bool = False

    model_config = ConfigDict(from_attributes=True)


class GroupCreate(Group):
    inbound_tags: list[str]

    @field_validator("inbound_tags", mode="after")
    @classmethod
    def inbound_tags_validator(cls, v):
        return ListValidator.not_null_list(v, "inbound")


class GroupModify(Group):
    @field_validator("inbound_tags", mode="after")
    @classmethod
    def inbound_tags_validator(cls, v):
        return ListValidator.nullable_list(v, "inbound")


class GroupResponse(Group):
    id: int
    total_users: int = 0

    model_config = ConfigDict(from_attributes=True)


class GroupsResponse(BaseModel):
    groups: list[GroupResponse]
    total: int


class GroupSimple(BaseModel):
    """Lightweight group model with only id and name for performance."""

    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class GroupsSimpleResponse(BaseModel):
    """Response model for lightweight group list."""

    groups: list[GroupSimple]
    total: int


class GroupSimpleSortField(str, Enum):
    id = "id"
    group_name = "name"


class SortDirection(str, Enum):
    asc = "asc"
    desc = "desc"


class GroupSimpleSortOption(str, Enum):
    id = "id"
    group_name = "name"
    desc_id = "-id"
    desc_group_name = "-name"

    @property
    def field(self) -> GroupSimpleSortField:
        return GroupSimpleSortField(self.value.lstrip("-"))

    @property
    def direction(self) -> SortDirection:
        return SortDirection.desc if self.value.startswith("-") else SortDirection.asc


class GroupListQuery(BaseModel):
    ids: list[int] | None = None
    offset: int | None = None
    limit: int | None = None


class GroupSimpleListQuery(BaseModel):
    ids: list[int] | None = None
    offset: int | None = None
    limit: int | None = None
    search: str | None = None
    sort: list[GroupSimpleSortOption] = Field(default_factory=list)
    all: bool = False

    @field_validator("sort", mode="before")
    @classmethod
    def validate_sort(cls, value):
        return ListValidator.normalize_enum_list_input(value, GroupSimpleSortOption)


class BulkGroup(BaseModel):
    group_ids: set[int]
    has_group_ids: set[int] = Field(default_factory=set)
    admins: set[int] = Field(default_factory=set)
    users: set[int] = Field(default_factory=set)
    dry_run: bool = False


class BulkGroupSelection(BaseModel):
    """Model for bulk group selection by IDs"""

    ids: set[int] = Field(default_factory=set)

    @field_validator("ids", mode="after")
    @classmethod
    def ids_validator(cls, v):
        return ListValidator.not_null_list(list(v), "group")


class RemoveGroupsResponse(BaseModel):
    """Response model for bulk group deletion"""

    groups: list[str]
    count: int


class BulkGroupsActionResponse(BaseModel):
    """Response model for bulk group actions."""

    groups: list[str]
    count: int
