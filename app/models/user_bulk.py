from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.db.models import DataLimitResetStrategy
from app.models.proxy import ShadowsocksMethods
from app.models.user import NextPlanModel, UserListQuery, UserStatusModify
from app.models.validators import MAX_ON_HOLD_EXPIRE_DURATION_SECONDS, OptionalAwareDatetime


class BulkEditModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BulkUserEditFilter(UserListQuery):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BulkUserSelection(BulkEditModel):
    ids: list[int] | None = Field(default=None, min_length=1)
    filters: BulkUserEditFilter | None = None

    @model_validator(mode="after")
    def validate_selection(self):
        if (self.ids is None) == (self.filters is None):
            raise ValueError("Provide either user IDs or filters")
        if self.ids is not None:
            if any(value <= 0 for value in self.ids):
                raise ValueError("User IDs must be positive")
            self.ids = sorted(set(self.ids))
        if self.filters is not None and (
            self.filters.offset or self.filters.limit or self.filters.sort or self.filters.load_sub
        ):
            raise ValueError("Bulk filters cannot include pagination, sorting or subscription loading")
        return self


class BulkNumericEdit(BulkEditModel):
    operation: Literal["set", "add", "subtract", "clear"]
    value: int | None = Field(default=None, ge=0, le=9_223_372_036_854_775_807)

    @model_validator(mode="after")
    def validate_value(self):
        if self.operation == "clear":
            if self.value is not None:
                raise ValueError("Clear does not accept a value")
        elif self.value is None or (self.operation != "set" and self.value == 0):
            raise ValueError("Provide a value (positive for relative changes)")
        return self


class BulkExpireEdit(BulkEditModel):
    operation: Literal["set", "add", "subtract", "clear"]
    value: OptionalAwareDatetime = None
    seconds: int | None = Field(default=None, gt=0, le=MAX_ON_HOLD_EXPIRE_DURATION_SECONDS)

    @model_validator(mode="after")
    def validate_value(self):
        if self.operation == "set":
            if self.value is None or self.seconds is not None:
                raise ValueError("Set expiration requires a date only")
        elif self.operation in {"add", "subtract"}:
            if self.seconds is None or self.value is not None:
                raise ValueError("Relative expiration requires seconds only")
        elif self.value is not None or self.seconds is not None:
            raise ValueError("Clear does not accept a value")
        return self


class BulkGroupsEdit(BulkEditModel):
    operation: Literal["set", "add", "remove", "clear"]
    ids: list[int] = Field(default_factory=list)
    remove_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_groups(self):
        if any(value <= 0 for value in self.ids + self.remove_ids):
            raise ValueError("Group IDs must be positive")
        if self.operation == "clear" and (self.ids or self.remove_ids):
            raise ValueError("Clear does not accept groups")
        if self.operation in {"add", "remove"} and not (self.ids or self.remove_ids):
            raise ValueError("Select at least one group")
        if self.remove_ids and self.operation != "add":
            raise ValueError("Additional removals are only supported with add")
        if set(self.ids) & set(self.remove_ids):
            raise ValueError("Cannot add and remove the same group")
        return self


class BulkNextPlan(NextPlanModel):
    user_template_id: int | None = Field(default=None, gt=0)
    data_limit: int | None = Field(default=None, ge=0, le=9_223_372_036_854_775_807)
    expire: int | None = Field(default=None, ge=0, le=MAX_ON_HOLD_EXPIRE_DURATION_SECONDS)
    model_config = ConfigDict(extra="forbid")


class BulkUserSettings(BulkEditModel):
    data_limit_reset_strategy: DataLimitResetStrategy | None = None
    hwid_limit: int | None = Field(default=None, ge=0, le=2_147_483_647)
    status: UserStatusModify | None = None
    note: str | None = Field(default=None, max_length=500)
    on_hold_expire_duration: int | None = Field(default=None, gt=0, le=MAX_ON_HOLD_EXPIRE_DURATION_SECONDS)
    on_hold_timeout: OptionalAwareDatetime = None
    auto_delete_in_days: int | None = Field(default=None, ge=0, le=2_147_483_647)
    next_plan: BulkNextPlan | None = None

    @model_validator(mode="after")
    def validate_nulls(self):
        for field in {"status", "data_limit_reset_strategy"} & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class BulkUsersEdit(BulkEditModel):
    selection: BulkUserSelection
    data_limit: BulkNumericEdit | None = None
    expire: BulkExpireEdit | None = None
    groups: BulkGroupsEdit | None = None
    settings: BulkUserSettings = Field(default_factory=BulkUserSettings)
    owner: str | None = Field(default=None, min_length=1, max_length=128)
    shadowsocks_method: ShadowsocksMethods | None = None
    preview_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_changes(self):
        if not any(
            (
                self.data_limit,
                self.expire,
                self.groups,
                self.settings.model_fields_set,
                self.owner,
                self.shadowsocks_method,
            )
        ):
            raise ValueError("Select at least one field to change")
        return self


class BulkUserEditChange(BulkEditModel):
    before: JsonValue
    after: JsonValue


class BulkUserEditSample(BulkEditModel):
    id: int
    username: str
    changes: dict[str, BulkUserEditChange]


class BulkUserEditError(BulkEditModel):
    id: int
    username: str
    detail: str


class BulkUsersEditResult(BulkEditModel):
    affected_users: int
    changed_users: int
    unchanged_users: int
    relative_skipped_users: int
    error_count: int
    errors: list[BulkUserEditError]
    samples: list[BulkUserEditSample]
    revision: str
    applied: bool = False
    sync_pending: bool = False
