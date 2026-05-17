from datetime import datetime as dt
from enum import Enum, IntEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.validators import ListValidator


class PermissionScope(IntEnum):
    """Scope for user-resource permissions. Stored as int in JSON for efficiency."""

    NONE = 0  # explicitly denied
    OWN = 1  # only own users (user.admin_id == admin.id)
    ALL = 2  # all users regardless of owner


class RoleLimits(BaseModel):
    max_users: int | None = None
    data_limit_min: int | None = None
    data_limit_max: int | None = None
    expire_days_min: int | None = None
    expire_days_max: int | None = None
    min_hwid_per_user: int | None = None
    max_hwid_per_user: int | None = None

    model_config = ConfigDict(from_attributes=True)


class RoleFeatures(BaseModel):
    can_use_reset_strategy: bool = True
    can_use_next_plan: bool = True

    model_config = ConfigDict(from_attributes=True)


class RoleAccess(BaseModel):
    require_template: bool = False
    allowed_template_ids: list[int] | None = None
    allowed_group_ids: list[int] | None = None

    model_config = ConfigDict(from_attributes=True)


# Each action value is either True (allowed, no scope) or {"scope": PermissionScope}
RoleActionValue = bool | dict[str, PermissionScope | int]
# Each resource maps action names to their permission value
RoleResourcePermissions = dict[str, RoleActionValue]


class RolePermissions(BaseModel):
    """
    Sparse permission map. Missing resource or action = denied.
    Each action value is True (allowed) or {"scope": "own"|"all"}.
    """

    users: RoleResourcePermissions | None = None
    admins: RoleResourcePermissions | None = None
    nodes: RoleResourcePermissions | None = None
    groups: RoleResourcePermissions | None = None
    hosts: RoleResourcePermissions | None = None
    templates: RoleResourcePermissions | None = None
    client_templates: RoleResourcePermissions | None = None
    cores: RoleResourcePermissions | None = None
    settings: RoleResourcePermissions | None = None
    system: RoleResourcePermissions | None = None
    hwids: RoleResourcePermissions | None = None
    admin_roles: RoleResourcePermissions | None = None

    model_config = ConfigDict(from_attributes=True, extra="allow")

    def get(self, resource: str, default: Any = None) -> RoleResourcePermissions | None:
        """Dict-like access so permissions.py can call permissions.get('users', {})."""
        return getattr(self, resource, None) if hasattr(self, resource) else default


class AdminRoleBase(BaseModel):
    name: str = Field(max_length=64)
    permissions: RolePermissions = Field(default_factory=RolePermissions)
    limits: RoleLimits = Field(default_factory=RoleLimits)
    features: RoleFeatures = Field(default_factory=RoleFeatures)
    access: RoleAccess = Field(default_factory=RoleAccess)

    model_config = ConfigDict(from_attributes=True)


class AdminRoleCreate(AdminRoleBase):
    pass


class AdminRoleModify(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    permissions: RolePermissions | None = None
    limits: RoleLimits | None = None
    features: RoleFeatures | None = None
    access: RoleAccess | None = None


class AdminRoleResponse(AdminRoleBase):
    id: int
    is_owner: bool
    created_at: dt

    model_config = ConfigDict(from_attributes=True)


class AdminRoleSimple(BaseModel):
    id: int
    name: str
    is_owner: bool

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
