import re
from enum import Enum, StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.proxy import ShadowsocksMethods, XTLSFlows

from .notification_enable import NotificationEnable
from .validators import DiscordValidator, ProxyValidator, URLValidator

TELEGRAM_TOKEN_PATTERN = r"^\d{8,12}:[A-Za-z0-9_-]{35}$"


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


class Discord(BaseModel):
    enable: bool = Field(default=False)
    token: str | None = Field(default=None)
    proxy_url: str | None = Field(default=None)

    @field_validator("proxy_url")
    @classmethod
    def validate_proxy_url(cls, v):
        return ProxyValidator.validate_proxy_url(v)

    @model_validator(mode="after")
    def check_enable_requires_token(self):
        if self.enable and not self.token:
            raise ValueError("Discord bot cannot be enabled without token.")
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
    core: NotificationChannel = Field(default_factory=NotificationChannel)
    group: NotificationChannel = Field(default_factory=NotificationChannel)
    host: NotificationChannel = Field(default_factory=NotificationChannel)
    node: NotificationChannel = Field(default_factory=NotificationChannel)
    user: NotificationChannel = Field(default_factory=NotificationChannel)
    user_template: NotificationChannel = Field(default_factory=NotificationChannel)


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
    sing_box = "sing_box"
    clash = "clash"
    clash_meta = "clash_meta"
    outline = "outline"
    block = "block"


class SubRule(BaseModel):
    pattern: str
    target: ConfigFormat


class SubFormatEnable(BaseModel):
    links: bool = Field(default=True)
    links_base64: bool = Field(default=True)
    xray: bool = Field(default=True)
    sing_box: bool = Field(default=True)
    clash: bool = Field(default=True)
    clash_meta: bool = Field(default=True)
    outline: bool = Field(default=True)


class Platform(StrEnum):
    ANDROID = "android"
    IOS = "ios"
    WIINDOWS = "windows"
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


class Application(BaseModel):
    name: str = Field(max_length=32)
    icon_url: str = Field(default="", max_length=512)
    import_url: str = Field(default="", max_length=256)
    description: dict[Language, str] = Field(default_factory=dict)
    recommended: bool = Field(False)
    platform: Platform
    download_links: list[DownloadLink]

    @field_validator("import_url")
    @classmethod
    def validate_import_url(cls, v: str) -> str:
        """Validate import_url contains {url} if not empty."""
        if v and "{url}" not in v:
            raise ValueError("import_url must contain {url} placeholder for URL replacement")
        return v


class Subscription(BaseModel):
    url_prefix: str = Field(default="")
    update_interval: int = Field(default=12)
    support_url: str = Field(default="https://t.me/")
    profile_title: str = Field(default="Subscription")
    # only supported by v2RayTun and Happ apps
    announce: str = Field(default="", max_length=128)
    announce_url: str = Field(default="")
    # Rules To Seperate Clients And Send Config As Needed
    rules: list[SubRule]
    manual_sub_request: SubFormatEnable = Field(default_factory=SubFormatEnable)
    applications: list[Application] = Field(default_factory=list)

    @field_validator("applications")
    @classmethod
    def validate_recommended_apps(cls, v: list[Application]) -> list[Application]:
        """Validate that each platform has at most one recommended application"""
        platform_recommended = {}

        for app in v:
            if app.recommended:
                if app.platform in platform_recommended:
                    raise ValueError(f"Multiple recommended applications found for platform '{app.platform}'.")
                platform_recommended[app.platform] = app.name

        return v


class General(BaseModel):
    default_flow: XTLSFlows = Field(default=XTLSFlows.NONE)
    default_method: ShadowsocksMethods = Field(default=ShadowsocksMethods.CHACHA20_POLY1305)


class SettingsSchema(BaseModel):
    telegram: Telegram | None = Field(default=None)
    discord: Discord | None = Field(default=None)
    webhook: Webhook | None = Field(default=None)
    notification_settings: NotificationSettings | None = Field(default=None)
    notification_enable: NotificationEnable | None = Field(default=None)
    subscription: Subscription | None = Field(default=None)
    general: General | None = Field(default=None)

    model_config = ConfigDict(from_attributes=True)
