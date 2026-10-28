import re
from enum import Enum, StrEnum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.models.host import validate_format_variables
from app.models.proxy import ShadowsocksMethods
from app.utils.helpers import has_oversized_format_spec

from .notification_enable import NotificationEnable
from .validators import DiscordValidator, ProxyValidator, URLValidator

TELEGRAM_TOKEN_PATTERN = r"^\d{8,12}:[A-Za-z0-9_-]{35}$"
BLOCKED_URL_SCHEMES = {"javascript", "data", "vbscript", "file", "blob"}
# An icon only ends up in <img src>, where a data: image is inert.
BLOCKED_ICON_URL_SCHEMES = BLOCKED_URL_SCHEMES - {"data"}

# Strict on input only: settings saved before these checks existed must still load (a failing load is a
# 500 on every subscription and on the settings page, with no way to fix it from the UI). Writes validate
# with this context (SettingsOperation.modify_settings); the subscription renderer neutralises old values.
SETTINGS_INPUT_CONTEXT = {"settings_input": True}


def _is_settings_input(info: ValidationInfo) -> bool:
    return bool(info.context and info.context.get("settings_input"))


def _validate_no_oversized_format_spec(value: str | None) -> str | None:
    if value and has_oversized_format_spec(value):
        raise ValueError("Format width or precision is too large")
    return value


def _validate_link_scheme(value: str, blocked_schemes: set[str] = BLOCKED_URL_SCHEMES) -> str:
    if not value:
        return value
    scheme = urlparse(value).scheme.lower()
    if scheme in blocked_schemes:
        raise ValueError(f"URL scheme '{scheme}' is not allowed")
    return value


def has_blocked_link_scheme(value: str, blocked_schemes: set[str] = BLOCKED_URL_SCHEMES) -> bool:
    """Render-time twin of _validate_link_scheme for values stored before the input check existed."""
    if not value:
        return False
    try:
        return urlparse(value).scheme.lower() in blocked_schemes
    except ValueError:
        return True


BUILTIN_FORMAT_VARIABLES = {
    "SERVER_IP",
    "SERVER_IPV6",
    "USERNAME",
    "DATA_USAGE",
    "DATA_LIMIT",
    "DATA_LEFT",
    "DAYS_LEFT",
    "EXPIRE_DATE",
    "JALALI_EXPIRE_DATE",
    "TIME_LEFT",
    "STATUS_EMOJI",
    "USAGE_PERCENTAGE",
    "ADMIN_USERNAME",
    "PROFILE_TITLE",
    "PROTOCOL",
    "TRANSPORT",
    "url",
    "format",
}
BUILTIN_CUSTOM_VARIABLE_KEYS = {variable.upper() for variable in BUILTIN_FORMAT_VARIABLES}


class RunMethod(StrEnum):
    WEBHOOK = "webhook"
    LONGPOLLING = "long-polling"


class Telegram(BaseModel):
    enable: bool = Field(default=False)
    token: str | None = Field(default=None)
    webhook_url: str | None = Field(default=None)
    webhook_secret: str | None = Field(default=None)
    proxy_url: str | None = Field(default=None)
    method: RunMethod = Field(default=RunMethod.WEBHOOK)

    mini_app_login: bool = Field(default=True)
    mini_app_web_url: str | None = Field(default="")

    for_admins_only: bool = Field(default=True)

    @field_validator("mini_app_web_url")
    @classmethod
    def validate_mini_app_web_url(cls, v):
        return URLValidator.validate_url(v)

    @field_validator("webhook_url")
    def validate_webhook_url(cls, v, values):
        method = values.data.get("method", "webhook")
        if method == "webhook":
            return URLValidator.validate_url(v)

    @field_validator("proxy_url")
    @classmethod
    def validate_proxy_url(cls, v):
        return ProxyValidator.validate_proxy_url(v)

    @field_validator("token")
    @classmethod
    def token_validation(cls, v):
        if not v:
            return v
        if not re.match(TELEGRAM_TOKEN_PATTERN, v):
            raise ValueError("Invalid telegram token format")
        return v

    @model_validator(mode="after")
    def check_enable_requires_token_and_url(self):
        if self.enable and (
            (self.method == RunMethod.WEBHOOK and (not self.token or not self.webhook_url or not self.webhook_secret))
            or (self.method == RunMethod.LONGPOLLING and not self.token)
        ):
            if self.method == RunMethod.WEBHOOK:
                raise ValueError("Telegram bot cannot be enabled without token, webhook_url and webhook_secret.")
            elif self.method == RunMethod.LONGPOLLING:
                raise ValueError("Telegram bot cannot be enabled without token.")
        return self


class WebhookInfo(BaseModel):
    url: str
    secret: str


class Webhook(BaseModel):
    enable: bool = Field(default=False)
    webhooks: list[WebhookInfo] = Field(default=[])
    days_left: list[int] = Field(default=[])
    usage_percent: list[int] = Field(default=[])
    timeout: int = Field(gt=0)
    recurrent: int = Field(gt=0)
    proxy_url: str | None = Field(default=None)

    @field_validator("proxy_url", mode="before")
    @classmethod
    def validate_proxy_url(cls, v):
        return ProxyValidator.validate_proxy_url(v)

    @model_validator(mode="after")
    def check_enable_requires_webhookinfo(self):
        if self.enable and (not self.webhooks or len(self.webhooks) == 0):
            raise ValueError("Webhook cannot be enabled without at least one WebhookInfo.")
        return self


class NotificationChannel(BaseModel):
    """Channel configuration for sending notifications to a specific entity"""

    telegram_chat_id: int | None = Field(default=None)
    telegram_topic_id: int | None = Field(default=None)
    discord_webhook_url: str | None = Field(default=None)

    @field_validator("discord_webhook_url", mode="before")
    @classmethod
    def validate_discord_webhook(cls, value):
        return DiscordValidator.validate_webhook(value)


class NotificationChannels(BaseModel):
    """Per-object notification channels"""

    admin: NotificationChannel = Field(default_factory=NotificationChannel)
    admin_role: NotificationChannel = Field(default_factory=NotificationChannel)
    core: NotificationChannel = Field(default_factory=NotificationChannel)
    group: NotificationChannel = Field(default_factory=NotificationChannel)
    host: NotificationChannel = Field(default_factory=NotificationChannel)
    node: NotificationChannel = Field(default_factory=NotificationChannel)
    user: NotificationChannel = Field(default_factory=NotificationChannel)
    user_template: NotificationChannel = Field(default_factory=NotificationChannel)
    api_key: NotificationChannel = Field(default_factory=NotificationChannel)


class NotificationSettings(BaseModel):
    # Define Which Notfication System Work's
    notify_telegram: bool = Field(default=False)
    notify_discord: bool = Field(default=False)

    # Telegram Settings
    telegram_api_token: str | None = Field(default=None)

    # Fallback Telegram Channel
    telegram_chat_id: int | None = Field(default=None)
    telegram_topic_id: int | None = Field(default=None)

    # Fallback Discord Settings
    discord_webhook_url: str | None = Field(default=None)

    # Per-object notification channels
    channels: NotificationChannels = Field(default_factory=NotificationChannels)

    # Proxy Settings
    proxy_url: str | None = Field(default=None)

    max_retries: int = Field(gt=1)

    @field_validator("proxy_url", mode="before")
    @classmethod
    def validate_proxy_url(cls, v):
        return ProxyValidator.validate_proxy_url(v)

    @field_validator("discord_webhook_url", mode="before")
    @classmethod
    def validate_discord_webhook(cls, value):
        return DiscordValidator.validate_webhook(value)

    @model_validator(mode="after")
    def check_notify_discord_requires_url(self):
        if self.notify_discord and not self.discord_webhook_url:
            raise ValueError("Discord notification cannot be enabled without webhook url.")
        return self

    @model_validator(mode="after")
    def check_notify_telegram_requires_token_and_id(self):
        if self.notify_telegram and not self.telegram_api_token:
            raise ValueError("Telegram notification cannot be enabled without token.")
        if self.notify_telegram and not self.telegram_chat_id:
            raise ValueError("Telegram notification cannot be enabled without chat id.")
        return self


class ConfigFormat(str, Enum):
    links = "links"
    links_base64 = "links_base64"
    xray = "xray"
    wireguard = "wireguard"
    sing_box = "sing_box"
    clash = "clash"
    clash_meta = "clash_meta"
    outline = "outline"
    block = "block"


class HeaderPlacement(StrEnum):
    header = "header"
    body_start = "body_start"
    body_end = "body_end"


class SubRule(BaseModel):
    pattern: str
    target: ConfigFormat
    response_headers: dict[str, Any] = Field(default_factory=dict)

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, value: str, info: ValidationInfo) -> str:
        # A stored pattern that does not compile is skipped by detect_client_rule.
        if not _is_settings_input(info):
            return value
        if not value or len(value) > 512:
            raise ValueError("pattern must be between 1 and 512 characters")
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regular expression: {exc}")
        return value


class SubFormatEnable(BaseModel):
    links: bool = Field(default=True)
    links_base64: bool = Field(default=True)
    xray: bool = Field(default=True)
    wireguard: bool = Field(default=True)
    sing_box: bool = Field(default=True)
    clash: bool = Field(default=True)
    clash_meta: bool = Field(default=True)
    outline: bool = Field(default=True)


class Platform(StrEnum):
    ANDROID = "android"
    IOS = "ios"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    APPLETV = "appletv"
    ANDROIDTV = "androidtv"


class Language(StrEnum):
    FA = "fa"
    EN = "en"
    RU = "ru"
    ZH = "zh"


class DownloadLink(BaseModel):
    name: str = Field(max_length=64)
    url: str
    language: Language

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str, info: ValidationInfo) -> str:
        return _validate_link_scheme(value) if _is_settings_input(info) else value


class Application(BaseModel):
    name: str = Field(max_length=32)
    icon_url: str = Field(default="", max_length=512)
    import_url: str = Field(default="", max_length=256)
    description: dict[Language, str] = Field(default_factory=dict)
    recommended: bool = Field(False)
    show_when_hwid_enabled: bool = Field(False)
    platform: Platform
    download_links: list[DownloadLink]

    @field_validator("icon_url")
    @classmethod
    def validate_icon_url(cls, v: str, info: ValidationInfo) -> str:
        return _validate_link_scheme(v, BLOCKED_ICON_URL_SCHEMES) if _is_settings_input(info) else v

    @field_validator("import_url")
    @classmethod
    def validate_import_url(cls, v: str, info: ValidationInfo) -> str:
        """Validate import_url contains {url} if not empty."""
        if v and "{url}" not in v:
            raise ValueError("import_url must contain {url} placeholder for URL replacement")
        if not _is_settings_input(info):
            # A stored value that cannot be formatted is served raw by _format_import_url.
            return v
        if v:
            # Rendered with str.format_map on every subscription page: no oversized widths, and no
            # attribute or index fields that fail (500) or allocate per request.
            validate_format_variables(v)
        return _validate_link_scheme(v)


class CustomVariable(BaseModel):
    key: str = Field(max_length=64)
    value: str = Field(default="", max_length=512)

    @field_validator("key", mode="before")
    @classmethod
    def normalize_key(cls, value):
        if not isinstance(value, str):
            raise TypeError("Variable key must be a string")
        value = value.strip()
        if value.startswith("{") and value.endswith("}"):
            value = value[1:-1].strip()
        return value.upper()

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", value):
            raise ValueError("Variable key must use uppercase letters, numbers, and underscores")
        return value

    @field_validator("value")
    @classmethod
    def validate_value_format(cls, value: str, info: ValidationInfo) -> str:
        if has_oversized_format_spec(value):
            # Checked before format_map, which would build the padded string first. Stored values load as raw text.
            if _is_settings_input(info):
                raise ValueError("Format width or precision is too large")
            return value
        try:
            value.format_map({key: "" for key in BUILTIN_FORMAT_VARIABLES})
        except KeyError:
            pass
        except ValueError, IndexError, AttributeError, TypeError:
            # Stray brace, {X[0]}, {X.y}: refused on input, kept as raw text when loading a stored value.
            if _is_settings_input(info):
                raise ValueError("Invalid formatting variables")
        return value


def validate_custom_variables(value: list[CustomVariable]) -> list[CustomVariable]:
    seen: set[str] = set()
    for variable in value:
        if variable.key.upper() in BUILTIN_CUSTOM_VARIABLE_KEYS:
            raise ValueError(f"Custom variable {variable.key} conflicts with a built-in variable")
        if variable.key in seen:
            raise ValueError(f"Duplicate custom variable {variable.key}")
        seen.add(variable.key)
    return value


class Subscription(BaseModel):
    url_prefix: str = Field(default="")
    update_interval: int = Field(default=12)
    support_url: str = Field(default="https://t.me/")
    profile_title: str = Field(default="Subscription")
    # only supported by v2RayTun and Happ apps
    announce: str = Field(default="", max_length=128)
    announce_url: str = Field(default="")
    response_headers: dict[str, Any] = Field(default_factory=dict)
    header_placement: HeaderPlacement = Field(default=HeaderPlacement.header)
    # Rules To Seperate Clients And Send Config As Needed
    rules: list[SubRule]
    manual_sub_request: SubFormatEnable = Field(default_factory=SubFormatEnable)
    applications: list[Application] = Field(default_factory=list)
    allow_browser_config: bool = Field(default=True)
    disable_sub_template: bool = Field(default=False)
    randomize_order: bool = Field(default=False)
    custom_variables: list[CustomVariable] = Field(default_factory=list)

    @field_validator("url_prefix")
    @classmethod
    def validate_url_prefix(cls, v: str) -> str:
        return v.strip("/")

    @field_validator("profile_title", "announce", "announce_url")
    @classmethod
    def validate_format_specs(cls, value: str, info: ValidationInfo) -> str:
        return _validate_no_oversized_format_spec(value) if _is_settings_input(info) else value

    @field_validator("announce_url", "support_url")
    @classmethod
    def validate_link_urls(cls, value: str, info: ValidationInfo) -> str:
        return _validate_link_scheme(value) if _is_settings_input(info) else value

    @field_validator("custom_variables")
    @classmethod
    def validate_custom_variables(cls, value: list[CustomVariable]) -> list[CustomVariable]:
        return validate_custom_variables(value)

    @field_validator("applications")
    @classmethod
    def validate_recommended_apps(cls, v: list[Application]) -> list[Application]:
        """Validate that each platform has at most one recommended app per subscription type."""
        platform_recommended = {}

        for app in v:
            if app.recommended:
                recommendation_key = (app.platform, app.show_when_hwid_enabled)
                if recommendation_key in platform_recommended:
                    subscription_type = "device-bound" if app.show_when_hwid_enabled else "standard"
                    raise ValueError(
                        f"Multiple recommended {subscription_type} applications found for platform '{app.platform}'."
                    )
                platform_recommended[recommendation_key] = app.name

        return v


class HWIDSettings(BaseModel):
    enabled: bool = Field(default=True)
    forced: bool = Field(default=False)
    require_hwid_for_manual_sub: bool = Field(default=False)
    fallback_limit: int | None = Field(default=None, ge=0)
    min_limit: int | None = Field(default=None, ge=0)
    max_limit: int | None = Field(default=None, ge=0)


class OnHoldTimeoutAction(StrEnum):
    activate = "activate"
    disable = "disable"
    delete = "delete"


class General(BaseModel):
    default_method: ShadowsocksMethods = Field(default=ShadowsocksMethods.CHACHA20_POLY1305)
    on_hold_timeout_action: OnHoldTimeoutAction = Field(default=OnHoldTimeoutAction.activate)
    custom_variables: list[CustomVariable] | None = Field(default=None)

    @field_validator("custom_variables")
    @classmethod
    def validate_custom_variables(cls, value: list[CustomVariable] | None) -> list[CustomVariable] | None:
        if value is None:
            return None
        return validate_custom_variables(value)


class SettingsSchema(BaseModel):
    telegram: Telegram | None = Field(default=None)
    webhook: Webhook | None = Field(default=None)
    notification_settings: NotificationSettings | None = Field(default=None)
    notification_enable: NotificationEnable | None = Field(default=None)
    subscription: Subscription | None = Field(default=None)
    hwid: HWIDSettings | None = Field(default=None)
    general: General | None = Field(default=None)

    model_config = ConfigDict(from_attributes=True)
