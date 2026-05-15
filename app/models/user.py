from datetime import datetime as dt
from enum import Enum
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models import DataLimitResetStrategy, UserStatus
from app.models.admin import AdminBase, AdminContactInfo
from app.models.proxy import ProxyTable, ShadowsocksMethods
from app.models.stats import Period
from app.utils.helpers import fix_datetime_timezone

from .validators import ListValidator, NumericValidatorMixin, UserValidator


class UserStatusModify(str, Enum):
    active = "active"
    disabled = "disabled"
    on_hold = "on_hold"


class NextPlanModel(BaseModel):
    user_template_id: int | None = Field(default=None)
    data_limit: int | None = Field(default=None)
    expire: int | None = Field(default=None)
    add_remaining_traffic: bool = False
    model_config = ConfigDict(from_attributes=True)


class User(BaseModel):
    proxy_settings: ProxyTable = Field(default_factory=ProxyTable)
    expire: dt | int | None = Field(default=None)
    data_limit: int | None = Field(ge=0, default=None, description="data_limit can be 0 or greater")
    data_limit_reset_strategy: DataLimitResetStrategy | None = Field(default=None)
    note: str | None = Field(max_length=500, default=None)
    on_hold_expire_duration: int | None = Field(default=None)
    on_hold_timeout: dt | int | None = Field(default=None)
    group_ids: list[int] | None = Field(default_factory=list)
    auto_delete_in_days: int | None = Field(default=None)
    hwid_limit: int | None = Field(default=None)
    next_plan: NextPlanModel | None = Field(default=None)


class UserWithValidator(User):
    @field_validator("on_hold_expire_duration")
    @classmethod
    def validate_timeout(cls, v):
        # Check if expire is 0 or None and timeout is not 0 or None
        if v in (0, None):
            return None
        return v

    @field_validator("on_hold_timeout", check_fields=False)
    @classmethod
    def validator_on_hold_timeout(cls, value):
        return UserValidator.validator_on_hold_timeout(value)

    @field_validator("expire", check_fields=False)
    @classmethod
    def validator_expire(cls, value):
        if not value:
            return value
        return fix_datetime_timezone(value)


class UserCreate(UserWithValidator):
    username: str
    status: UserStatus | None = Field(default=None)

    @field_validator("username", check_fields=False)
    @classmethod
    def validate_username(cls, v):
        return UserValidator.validate_username(v)

    @field_validator("status", mode="before", check_fields=False)
    def validate_status(cls, status, values):
        return UserValidator.validate_status(status, {UserStatus.active, UserStatus.on_hold}, values)

    @field_validator("group_ids", mode="after")
    @classmethod
    def group_ids_validator(cls, v):
        return ListValidator.not_null_list(v, "group")


class UserModify(UserWithValidator):
    status: UserStatus | None = Field(default=None)
    proxy_settings: ProxyTable | None = Field(default=None)

    @field_validator("status", mode="before", check_fields=False)
    def validate_status(cls, status, values):
        return UserValidator.validate_status(
            status, {UserStatus.active, UserStatus.on_hold, UserStatus.disabled}, values
        )

    @field_validator("group_ids", mode="after")
    @classmethod
    def group_ids_validator(cls, v):
        return ListValidator.nullable_list(v, "group")


class UserNotificationResponse(User):
    id: int
    username: str
    status: UserStatus
    used_traffic: int
    lifetime_used_traffic: int = Field(default=0)
    created_at: dt
    edit_at: dt | None = Field(default=None)
    online_at: dt | None = Field(default=None)
    subscription_url: str = Field(default="")
    admin: AdminContactInfo | None = Field(default=None)
    group_names: list[str] | None = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)

    @field_validator("used_traffic", "lifetime_used_traffic", "data_limit", mode="before")
    @classmethod
    def cast_to_int(cls, v):
        return NumericValidatorMixin.cast_to_int(v)

    @field_validator("created_at", "edit_at", "online_at", mode="before")
    @classmethod
    def validator_date(cls, v):
        if not v:
            return v
        return fix_datetime_timezone(v)


class UserResponse(UserNotificationResponse):
    admin: AdminBase | None = Field(default=None)
    group_names: list[str] | None = Field(default=None, exclude=True)


class SubscriptionUserResponse(UserResponse):
    admin: AdminContactInfo | None = Field(default=None, exclude=True)
    note: str | None = Field(None, exclude=True)
    auto_delete_in_days: int | None = Field(None, exclude=True)
    subscription_url: str | None = Field(None, exclude=True)
    ip: str | None = Field(default=None)
    model_config = ConfigDict(from_attributes=True)


class UsersResponseWithInbounds(SubscriptionUserResponse):
    inbounds: list[str] | None = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class UsersResponse(BaseModel):
    users: list[UserResponse]
    total: int


class UserSimple(BaseModel):
    """Lightweight user model with only id and username for performance."""

    id: int
    username: str
    model_config = ConfigDict(from_attributes=True)


class UsersSimpleResponse(BaseModel):
    """Response model for lightweight user list."""

    users: list[UserSimple]
    total: int


class UserSortField(str, Enum):
    username = "username"
    used_traffic = "used_traffic"
    data_limit = "data_limit"
    expire = "expire"
    created_at = "created_at"
    edit_at = "edit_at"
    online_at = "online_at"


class UserSimpleSortField(str, Enum):
    id = "id"
    username = "username"


class SortDirection(str, Enum):
    asc = "asc"
    desc = "desc"


class UserSortOption(str, Enum):
    username = "username"
    used_traffic = "used_traffic"
    data_limit = "data_limit"
    expire = "expire"
    created_at = "created_at"
    edit_at = "edit_at"
    online_at = "online_at"
    desc_username = "-username"
    desc_used_traffic = "-used_traffic"
    desc_data_limit = "-data_limit"
    desc_expire = "-expire"
    desc_created_at = "-created_at"
    desc_edit_at = "-edit_at"
    desc_online_at = "-online_at"

    @property
    def field(self) -> UserSortField:
        return UserSortField(self.value.lstrip("-"))

    @property
    def direction(self) -> SortDirection:
        return SortDirection.desc if self.value.startswith("-") else SortDirection.asc


class UserSimpleSortOption(str, Enum):
    id = "id"
    username = "username"
    desc_id = "-id"
    desc_username = "-username"

    @property
    def field(self) -> UserSimpleSortField:
        return UserSimpleSortField(self.value.lstrip("-"))

    @property
    def direction(self) -> SortDirection:
        return SortDirection.desc if self.value.startswith("-") else SortDirection.asc


class UserListQuery(BaseModel):
    offset: int | None = Field(default=None)
    limit: int | None = Field(default=None)
    ids: list[int] | None = Field(default=None)
    username: list[str] | None = Field(default=None)
    usernames: list[str] | None = Field(default=None)
    owner: list[str] | None = Field(default=None, alias="admin")
    admin_ids: list[int] | None = Field(default=None, validation_alias=AliasChoices("admin_ids", "admin_id"))
    group_ids: list[int] | None = Field(default=None, alias="group")
    search: str | None = Field(default=None)
    status: UserStatus | list[UserStatus] | None = Field(default=None)
    sort: list[UserSortOption] = Field(default_factory=list)
    proxy_id: str | None = Field(default=None)
    data_limit_reset_strategy: DataLimitResetStrategy | list[DataLimitResetStrategy] | None = Field(
        default=None, validation_alias=AliasChoices("data_limit_reset_strategy", "reset_strategy")
    )
    data_limit_min: int | None = Field(default=None, ge=0)
    data_limit_max: int | None = Field(default=None, ge=0)
    expire_after: dt | None = Field(default=None, examples=["2026-01-01T00:00:00+03:30"])
    expire_before: dt | None = Field(default=None, examples=["2026-01-31T23:59:59+03:30"])
    online_after: dt | None = Field(default=None, examples=["2026-01-01T00:00:00+03:30"])
    online_before: dt | None = Field(default=None, examples=["2026-01-31T23:59:59+03:30"])
    online: bool = Field(default=False)
    no_data_limit: bool = Field(default=False)
    no_expire: bool = Field(default=False)
    load_sub: bool = Field(default=False)
    model_config = ConfigDict(populate_by_name=True)

    @field_validator("expire_after", "expire_before", "online_after", "online_before", mode="before")
    @classmethod
    def validate_datetimes(cls, value):
        if not value:
            return value
        return fix_datetime_timezone(value)

    @field_validator("sort", mode="before")
    @classmethod
    def validate_sort(cls, value):
        return ListValidator.normalize_enum_list_input(value, UserSortOption)


class UserSimpleListQuery(BaseModel):
    ids: list[int] | None = Field(default=None)
    usernames: list[str] | None = Field(default=None)
    offset: int | None = Field(default=None)
    limit: int | None = Field(default=None)
    search: str | None = Field(default=None)
    sort: list[UserSimpleSortOption] = Field(default_factory=list)
    all: bool = Field(default=False)

    @field_validator("sort", mode="before")
    @classmethod
    def validate_sort(cls, value):
        return ListValidator.normalize_enum_list_input(value, UserSimpleSortOption)


class UserUsageQuery(BaseModel):
    period: Period = Field(default=Period.hour)
    node_id: int | None = Field(default=None)
    group_by_node: bool = Field(default=False)
    start: dt | None = Field(default=None, examples=["2024-01-01T00:00:00+03:30"])
    end: dt | None = Field(default=None, examples=["2024-01-31T23:59:59+03:30"])

    @field_validator("start", "end", mode="before")
    @classmethod
    def validate_datetimes(cls, value):
        if not value:
            return value
        return fix_datetime_timezone(value)


class UsersUsageQuery(UserUsageQuery):
    owner: list[str] | None = Field(default=None, alias="admin")
    model_config = ConfigDict(populate_by_name=True)


class ExpiredUsersQuery(BaseModel):
    admin_username: str | None = Field(default=None)
    target: Literal["expired", "limited"] = Field(default="expired")
    expired_after: dt | None = Field(default=None, examples=["2024-01-01T00:00:00+03:30"])
    expired_before: dt | None = Field(default=None, examples=["2024-01-31T23:59:59+03:30"])

    @field_validator("expired_after", "expired_before", mode="before")
    @classmethod
    def validate_datetimes(cls, value):
        if not value:
            return value
        return fix_datetime_timezone(value)


class UserSubscriptionUpdateSchema(BaseModel):
    created_at: dt
    user_agent: str
    ip: str | None = Field(default=None)
    hwid: str | None = Field(default=None)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", mode="before")
    @classmethod
    def validator_date(cls, v):
        if not v:
            return v
        return fix_datetime_timezone(v)


class UserSubscriptionUpdateList(BaseModel):
    updates: list[UserSubscriptionUpdateSchema] = Field(default_factory=list)
    count: int


class UserSubscriptionUpdateChartSegment(BaseModel):
    name: str
    count: int
    percentage: float


class UserSubscriptionUpdateChart(BaseModel):
    total: int
    segments: list[UserSubscriptionUpdateChartSegment] = Field(default_factory=list)


class UserHWIDResponse(BaseModel):
    id: int
    hwid: str
    device_os: str | None = None
    os_version: str | None = None
    device_model: str | None = None
    created_at: dt
    last_used_at: dt
    model_config = ConfigDict(from_attributes=True)


class UserHWIDListResponse(BaseModel):
    hwids: list[UserHWIDResponse]
    count: int


class RemoveUsersResponse(BaseModel):
    users: list[str]
    count: int


class BulkUsersActionResponse(BaseModel):
    users: list[str]
    count: int


class BulkUsersSelection(BaseModel):
    ids: set[int] = Field(default_factory=set)

    @field_validator("ids", mode="after")
    @classmethod
    def ids_validator(cls, v):
        return ListValidator.not_null_list(v, "user")


class BulkUsersSetOwner(BulkUsersSelection):
    admin_username: str

    @field_validator("admin_username", check_fields=False)
    @classmethod
    def validate_admin_username(cls, v):
        return UserValidator.validate_username(v)


class ModifyUserByTemplate(BaseModel):
    user_template_id: int
    note: str | None = Field(max_length=500, default=None)


class BulkUsersApplyTemplate(BulkUsersSelection, ModifyUserByTemplate):
    """Apply a user template to a selection of existing users (by ID)."""


class CreateUserFromTemplate(ModifyUserByTemplate):
    username: str

    @field_validator("username", check_fields=False)
    @classmethod
    def validate_username(cls, v):
        return UserValidator.validate_username(v)


class BulkUserFilter(BaseModel):
    dry_run: bool = False
    group_ids: set[int] = Field(default_factory=set)
    admins: set[int] = Field(default_factory=set)
    users: set[int] = Field(default_factory=set)
    status: set[UserStatus] = Field(default_factory=set)
    expire_after: dt | None = Field(default=None, validation_alias=AliasChoices("expire_after", "expired_after"))
    expire_before: dt | None = Field(default=None, validation_alias=AliasChoices("expire_before", "expired_before"))

    @field_validator("expire_after", "expire_before", check_fields=False)
    @classmethod
    def validator_datetime(cls, value):
        if not value:
            return value
        return fix_datetime_timezone(value)


class BulkUser(BulkUserFilter):
    amount: int


class BulkUsersProxy(BulkUserFilter):
    method: ShadowsocksMethods | None = Field(default=None)


class BulkWireGuardPeerIPs(BulkUserFilter):
    """Re-seat WireGuard peer IPs (same scoping as BulkUser: users, admins, group_ids, status)."""

    confirm: bool = False
    replace_all: bool = False


class BulkOperationDryRunResponse(BaseModel):
    """Preview for bulk user/group operations (no DB writes)."""

    dry_run: bool = True
    affected_users: int


class WireGuardPeerIPsReallocateResponse(BaseModel):
    wireguard_inbound_tags: int
    candidates: int
    updated: int
    dry_run: bool
    sample_usernames: list[str]
    affected_users: int


class UsernameGenerationStrategy(str, Enum):
    random = "random"
    sequence = "sequence"


class BulkCreationBase(BaseModel):
    count: int = Field(gt=0, le=500)
    strategy: UsernameGenerationStrategy = Field(default=UsernameGenerationStrategy.random)


class BulkUsersFromTemplate(BulkCreationBase, CreateUserFromTemplate):
    username: str | None = Field(default=None)
    start_number: int | None = Field(
        default=None,
        ge=0,
        description="Starting suffix for sequence strategy (defaults to 1; base username digits are ignored)",
    )

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        # Skip validation if username is None (for random strategy)
        if v is None:
            return v
        return UserValidator.validate_username(username=v, len_check=False)

    @model_validator(mode="after")
    def validate_username_strategy(self):
        if self.strategy == UsernameGenerationStrategy.random:
            if self.username not in (None, ""):
                raise ValueError("username must be null when strategy is 'random'")
            if self.start_number is not None:
                raise ValueError("start_number is only valid when strategy is 'sequence'")
        if self.strategy == UsernameGenerationStrategy.sequence and not self.username:
            raise ValueError("username is required when strategy is 'sequence'")
        return self


class BulkUsersCreateResponse(BaseModel):
    subscription_urls: list[str] = Field(default_factory=list)
    created: int = Field(default=0)
