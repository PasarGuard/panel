from datetime import datetime as dt
from enum import Enum, IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.settings import HWIDSettings
from app.models.validators import ListValidator


class HWIDMode(StrEnum):
    DISABLED = "disabled"
    USE_GLOBAL = "use_global"
    OVERRIDE = "override"


class RoleHWIDSettings(HWIDSettings):
    mode: HWIDMode = Field(default=HWIDMode.USE_GLOBAL)


class PermissionScope(IntEnum):
    """Scope for user-resource permissions. Stored as int in JSON for efficiency."""

    NONE = 0  # explicitly denied
    OWN = 1  # only own users (user.admin_id == admin.id)
    ALL = 2  # all users regardless of owner


# Action value: True = allowed (no scope), {"scope": N} = scoped, None/missing = denied
RoleActionValue = bool | dict[str, PermissionScope | int]


class _ResourcePermissions(BaseModel):
    """Base for all per-resource permission models. Provides dict-like .get() for the enforcement layer."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    def get(self, action: str, default: Any = None) -> RoleActionValue | None:
        """Return the permission value for an action, or default if not set."""
        return getattr(self, action, default)


class CRUDPermissions(_ResourcePermissions):
    """Standard create/read/read_simple/update/delete permissions.
    Used directly by: groups, templates, client_templates, cores, admin_roles.
    Also serves as base for resources with additional actions."""

    create: RoleActionValue | None = None
    read: RoleActionValue | None = None
    read_simple: RoleActionValue | None = None
    update: RoleActionValue | None = None
    delete: RoleActionValue | None = None


class UsersPermissions(CRUDPermissions):
    reset_usage: RoleActionValue | None = None
    revoke_sub: RoleActionValue | None = None
    set_owner: RoleActionValue | None = None
    activate_next_plan: RoleActionValue | None = None


class AdminsPermissions(CRUDPermissions):
    reset_usage: RoleActionValue | None = None


class NodesPermissions(CRUDPermissions):
    reconnect: RoleActionValue | None = None
    update_core: RoleActionValue | None = None
    logs: RoleActionValue | None = None
    stats: RoleActionValue | None = None


class HostsPermissions(_ResourcePermissions):
    create: RoleActionValue | None = None
    read: RoleActionValue | None = None
    update: RoleActionValue | None = None


class SettingsPermissions(_ResourcePermissions):
    read: RoleActionValue | None = None
    read_general: RoleActionValue | None = None
    update: RoleActionValue | None = None


class SystemPermissions(_ResourcePermissions):
    read: RoleActionValue | None = None


class HwidsPermissions(_ResourcePermissions):
    read: RoleActionValue | None = None
    delete: RoleActionValue | None = None


class RoleLimits(BaseModel):
    max_users: int | None = None
    data_limit_min: int | None = None
    data_limit_max: int | None = None
    expire_min: int | None = None
    expire_max: int | None = None
    min_hwid_per_user: int | None = None
    max_hwid_per_user: int | None = None
    on_hold_timeout_min: int | None = None
    on_hold_timeout_max: int | None = None

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


class RolePermissions(BaseModel):
    """
    Typed permission map. Missing resource or action = denied.
    Each action value is True (allowed), {"scope": N} (scoped), or None (denied).
    """

    users: UsersPermissions | None = None
    admins: AdminsPermissions | None = None
    nodes: NodesPermissions | None = None
    groups: CRUDPermissions | None = None
    hosts: HostsPermissions | None = None
    templates: CRUDPermissions | None = None
    client_templates: CRUDPermissions | None = None
    cores: CRUDPermissions | None = None
    settings: SettingsPermissions | None = None
    system: SystemPermissions | None = None
    hwids: HwidsPermissions | None = None
    admin_roles: CRUDPermissions | None = None

    model_config = ConfigDict(from_attributes=True)

    def get(self, resource: str, default: Any = None) -> _ResourcePermissions | None:
        """Dict-like access so permissions.py can call permissions.get('users')."""
        return getattr(self, resource, default)


class AdminRoleBase(BaseModel):
    name: str = Field(max_length=64)
    permissions: RolePermissions = Field(default_factory=RolePermissions)
    limits: RoleLimits = Field(default_factory=RoleLimits)
    features: RoleFeatures = Field(default_factory=RoleFeatures)
    access: RoleAccess = Field(default_factory=RoleAccess)
    hwid: RoleHWIDSettings = Field(default_factory=RoleHWIDSettings)
    disabled_when_limited: bool = False
    disconnect_users_when_limited: bool = True
    disconnect_users_when_disabled: bool = True

    model_config = ConfigDict(from_attributes=True)


class AdminRoleCreate(AdminRoleBase):
    pass


class AdminRoleModify(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    permissions: RolePermissions | None = None
    limits: RoleLimits | None = None
    features: RoleFeatures | None = None
    access: RoleAccess | None = None
    hwid: RoleHWIDSettings | None = None
    disabled_when_limited: bool | None = None
    disconnect_users_when_limited: bool | None = None
    disconnect_users_when_disabled: bool | None = None


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
