from datetime import datetime as dt
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.validators import ListValidator


class RoleLimits(BaseModel):
    max_users: int | None = None
    data_limit_min: int | None = None
    data_limit_max: int | None = None
    expire_days_min: int | None = None
    expire_days_max: int | None = None
    max_hwid_per_user: int | None = None


class RoleFeatures(BaseModel):
    can_use_reset_strategy: bool = True
    can_use_next_plan: bool = True


class RoleAccess(BaseModel):
    require_template: bool = False
    allowed_template_ids: list[int] | None = None
    allowed_group_ids: list[int] | None = None


class AdminRoleBase(BaseModel):
    name: str = Field(max_length=64)
    permissions: dict = Field(default_factory=dict)
    limits: RoleLimits = Field(default_factory=RoleLimits)
    features: RoleFeatures = Field(default_factory=RoleFeatures)
    access: RoleAccess = Field(default_factory=RoleAccess)


class AdminRoleCreate(AdminRoleBase):
    pass


class AdminRoleModify(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    permissions: dict | None = None
    limits: RoleLimits | None = None
    features: RoleFeatures | None = None
    access: RoleAccess | None = None


class AdminRoleResponse(AdminRoleBase):
    id: int
    is_locked: bool
    created_at: dt

    model_config = ConfigDict(from_attributes=True)


class AdminRoleSimple(BaseModel):
    id: int
    name: str
    is_locked: bool
    model_config = ConfigDict(from_attributes=True)


# --- List query ---


class AdminRoleSortField(str, Enum):
    id = "id"
    name = "name"
    created_at = "created_at"


class AdminRoleSortOption(str, Enum):
    id = "id"
    name = "name"
    created_at = "created_at"
    desc_id = "-id"
    desc_name = "-name"
    desc_created_at = "-created_at"

    @property
    def field(self) -> AdminRoleSortField:
        return AdminRoleSortField(self.value.lstrip("-"))

    @property
    def is_desc(self) -> bool:
        return self.value.startswith("-")


class AdminRoleListQuery(BaseModel):
    search: str | None = None
    offset: int | None = None
    limit: int | None = None
    sort: list[AdminRoleSortOption] = Field(default_factory=list)

    @field_validator("sort", mode="before")
    @classmethod
    def validate_sort(cls, value):
        return ListValidator.normalize_enum_list_input(value, AdminRoleSortOption)


class AdminRolesResponse(BaseModel):
    roles: list[AdminRoleResponse]
    total: int


class AdminRolesSimpleResponse(BaseModel):
    roles: list[AdminRoleSimple]
    total: int
