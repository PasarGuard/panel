import re
from datetime import datetime as dt
from enum import Enum, StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .settings import CustomVariable, validate_custom_variables
from .validators import ListValidator

# Same token rule as BaseOperation._HTTP_HEADER_NAME_PATTERN, which checks the final response headers.
_HTTP_HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


class ClientProfileTemplateType(StrEnum):
    """Client template types that render a whole subscription config (clash covers clash and clash_meta)."""

    xray_subscription = "xray_subscription"
    singbox_subscription = "singbox_subscription"
    clash_subscription = "clash_subscription"


def _validate_header_name(name: str) -> str:
    if not isinstance(name, str) or not name or name != name.strip():
        raise ValueError("Invalid response header name: empty or whitespace wrapped")
    if not _HTTP_HEADER_NAME_PATTERN.fullmatch(name):
        raise ValueError(f'Invalid response header name "{name}"')
    return name


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    return value if value.strip() else None


class ClientProfileSettings(BaseModel):
    """Delivery overrides; None (or an empty string) means inherit from the admin/global settings."""

    profile_title: str | None = Field(default=None, max_length=256)
    support_url: str | None = Field(default=None, max_length=512)
    announce: str | None = Field(default=None, max_length=128)
    announce_url: str | None = Field(default=None, max_length=512)
    update_interval: int | None = Field(default=None, ge=1)
    randomize_order: bool | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    remove_response_headers: list[str] = Field(default_factory=list)
    custom_variables: list[CustomVariable] = Field(default_factory=list)

    @field_validator("profile_title", "support_url", "announce", "announce_url")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @field_validator("response_headers")
    @classmethod
    def validate_response_headers(cls, value: dict[str, str]) -> dict[str, str]:
        for name, header_value in value.items():
            _validate_header_name(name)
            if "\r" in header_value or "\n" in header_value or "\x00" in header_value:
                raise ValueError(f'Invalid response header "{name}": value contains forbidden control characters')
        return value

    @field_validator("remove_response_headers")
    @classmethod
    def validate_remove_response_headers(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        cleaned: list[str] = []
        for name in value:
            _validate_header_name(name)
            if name.lower() not in seen:
                seen.add(name.lower())
                cleaned.append(name)
        return cleaned

    @field_validator("custom_variables")
    @classmethod
    def validate_custom_variables(cls, value: list[CustomVariable]) -> list[CustomVariable]:
        return validate_custom_variables(value)


def _validate_name(value: str | None) -> str | None:
    if value is None:
        return value
    stripped = value.strip()
    if not stripped:
        raise ValueError("name can't be empty")
    return stripped


class ClientProfileBase(BaseModel):
    name: str = Field(max_length=64)
    note: str | None = Field(default=None, max_length=500)
    templates: dict[ClientProfileTemplateType, int] = Field(default_factory=dict)
    settings: ClientProfileSettings = Field(default_factory=ClientProfileSettings)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _validate_name(value)


class ClientProfileCreate(ClientProfileBase):
    pass


class ClientProfileModify(BaseModel):
    """Partial update: omitted fields are unchanged; templates/settings replace the stored value as a whole."""

    name: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=500)
    templates: dict[ClientProfileTemplateType, int] | None = None
    settings: ClientProfileSettings | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return _validate_name(value)


class ClientProfile(BaseModel):
    """Profile as used when building a subscription (also the cached shape)."""

    id: int
    name: str
    note: str | None = None
    templates: dict[ClientProfileTemplateType, int] = Field(default_factory=dict)
    settings: ClientProfileSettings = Field(default_factory=ClientProfileSettings)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("templates", mode="before")
    @classmethod
    def validate_templates(cls, value):
        return value or {}

    @field_validator("settings", mode="before")
    @classmethod
    def validate_settings(cls, value):
        return value or {}


class ClientProfileResponse(ClientProfile):
    created_at: dt
    users_count: int = 0


class ClientProfileResponseList(BaseModel):
    count: int
    profiles: list[ClientProfileResponse] = []


class ClientProfileSimple(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class ClientProfilesSimpleResponse(BaseModel):
    profiles: list[ClientProfileSimple]
    total: int


class ClientProfileSimpleSortField(str, Enum):
    id = "id"
    profile_name = "name"


class ClientProfileSimpleSortOption(str, Enum):
    id = "id"
    profile_name = "name"
    desc_id = "-id"
    desc_profile_name = "-name"

    @property
    def field(self) -> ClientProfileSimpleSortField:
        return ClientProfileSimpleSortField(self.value.lstrip("-"))


class ClientProfileListQuery(BaseModel):
    ids: list[int] | None = None
    search: str | None = None
    offset: int | None = None
    limit: int | None = None


class ClientProfileSimpleListQuery(BaseModel):
    ids: list[int] | None = None
    offset: int | None = None
    limit: int | None = None
    search: str | None = None
    sort: list[ClientProfileSimpleSortOption] = Field(default_factory=list)
    all: bool = False

    @field_validator("sort", mode="before")
    @classmethod
    def validate_sort(cls, value):
        return ListValidator.normalize_enum_list_input(value, ClientProfileSimpleSortOption)


class BulkClientProfileSelection(BaseModel):
    """Model for bulk client profile selection by IDs"""

    ids: set[int] = Field(default_factory=set)

    @field_validator("ids", mode="after")
    @classmethod
    def ids_validator(cls, v):
        return ListValidator.not_null_list(list(v), "profile")


class RemoveClientProfilesResponse(BaseModel):
    """Response model for bulk client profile deletion"""

    profiles: list[str]
    count: int


class ClientProfileAssignUsers(BaseModel):
    """Attach the listed users to the profile."""

    user_ids: set[int] = Field(default_factory=set)

    @field_validator("user_ids", mode="after")
    @classmethod
    def user_ids_validator(cls, v):
        return ListValidator.not_null_list(list(v), "user")


class ClientProfileUnassignUsers(BaseModel):
    """Detach the listed users (or, with all=true, every user) from the profile."""

    user_ids: set[int] = Field(default_factory=set)
    all: bool = False

    @model_validator(mode="after")
    def validate_selection(self):
        if self.all and self.user_ids:
            raise ValueError("user_ids must be empty when all is true")
        if not self.all and not self.user_ids:
            raise ValueError("user_ids is required unless all is true")
        return self


class ClientProfileUsersResponse(BaseModel):
    count: int
