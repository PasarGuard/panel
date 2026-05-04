"""init settings

Revision ID: 9af04c077ede
Revises: beb47f520963
Create Date: 2025-05-08 19:01:36.454848

"""

from functools import cached_property

from alembic import op
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9af04c077ede"
down_revision = "beb47f520963"
branch_labels = None
depends_on = None


class MigrationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_api_token: str = Field(default="", validation_alias="TELEGRAM_API_TOKEN")
    telegram_webhook_url: str = Field(default="", validation_alias="TELEGRAM_WEBHOOK_URL")
    telegram_webhook_secret_key: str | None = Field(default=None, validation_alias="TELEGRAM_WEBHOOK_SECRET_KEY")
    telegram_admin_id_raw: str = Field(default="", validation_alias="TELEGRAM_ADMIN_ID")
    telegram_proxy_url: str | None = Field(default=None, validation_alias="TELEGRAM_PROXY_URL")
    telegram_logger_channel_id: int = Field(default=0, validation_alias="TELEGRAM_LOGGER_CHANNEL_ID")
    telegram_logger_topic_id: int = Field(default=0, validation_alias="TELEGRAM_LOGGER_TOPIC_ID")
    telegram_notify: bool = Field(default=False, validation_alias="TELEGRAM_NOTIFY")

    webhook_address_raw: str = Field(default="", validation_alias="WEBHOOK_ADDRESS")
    webhook_secret: str | None = Field(default=None, validation_alias="WEBHOOK_SECRET")
    webhook_proxy_url: str | None = Field(default=None, validation_alias="WEBHOOK_PROXY_URL")
    notification_proxy_url: str | None = Field(default=None, validation_alias="NOTIFICATION_PROXY_URL")
    recurrent_notifications_timeout: int = Field(default=180, validation_alias="RECURRENT_NOTIFICATIONS_TIMEOUT")
    number_of_recurrent_notifications: int = Field(default=3, validation_alias="NUMBER_OF_RECURRENT_NOTIFICATIONS")
    notify_reached_usage_percent_raw: str = Field(default="80", validation_alias="NOTIFY_REACHED_USAGE_PERCENT")
    notify_days_left_raw: str = Field(default="3", validation_alias="NOTIFY_DAYS_LEFT")
    discord_webhook_url: str = Field(default="", validation_alias="DISCORD_WEBHOOK_URL")

    xray_subscription_url_prefix: str = Field(default="", validation_alias="XRAY_SUBSCRIPTION_URL_PREFIX")
    sub_update_interval: str = Field(default="12", validation_alias="SUB_UPDATE_INTERVAL")
    sub_support_url: str = Field(default="https://t.me/", validation_alias="SUB_SUPPORT_URL")
    sub_profile_title: str = Field(default="Subscription", validation_alias="SUB_PROFILE_TITLE")
    host_status_filter: bool = Field(default=True, validation_alias="HOST_STATUS_FILTER")

    use_custom_json_default: bool = Field(default=False, validation_alias="USE_CUSTOM_JSON_DEFAULT")
    use_custom_json_for_v2rayn: bool = Field(default=False, validation_alias="USE_CUSTOM_JSON_FOR_V2RAYN")
    use_custom_json_for_v2rayng: bool = Field(default=False, validation_alias="USE_CUSTOM_JSON_FOR_V2RAYNG")
    use_custom_json_for_streisand: bool = Field(default=False, validation_alias="USE_CUSTOM_JSON_FOR_STREISAND")
    use_custom_json_for_happ: bool = Field(default=False, validation_alias="USE_CUSTOM_JSON_FOR_HAPP")
    use_custom_json_for_npvtunnel: bool = Field(default=False, validation_alias="USE_CUSTOM_JSON_FOR_NPVTUNNEL")

    @cached_property
    def telegram_admin_id(self) -> int | None:
        if not self.telegram_admin_id_raw.strip():
            return None
        return int(self.telegram_admin_id_raw.split(",")[0].strip())

    @cached_property
    def webhook_address(self) -> list[str]:
        return [address.strip() for address in self.webhook_address_raw.split(",") if address.strip()]

    @cached_property
    def notify_reached_usage_percent(self) -> list[int]:
        return [int(percent.strip()) for percent in self.notify_reached_usage_percent_raw.split(",") if percent.strip()]

    @cached_property
    def notify_days_left(self) -> list[int]:
        return [int(days.strip()) for days in self.notify_days_left_raw.split(",") if days.strip()]


migration_settings = MigrationSettings()


# Environment variables management
TELEGRAM_API_TOKEN = migration_settings.telegram_api_token
TELEGRAM_WEBHOOK_URL = migration_settings.telegram_webhook_url.strip("/")
TELEGRAM_WEBHOOK_SECRET_KEY = migration_settings.telegram_webhook_secret_key
TELEGRAM_ADMIN_ID = migration_settings.telegram_admin_id
TELEGRAM_PROXY_URL = migration_settings.telegram_proxy_url
TELEGRAM_LOGGER_CHANNEL_ID = migration_settings.telegram_logger_channel_id
TELEGRAM_LOGGER_TOPIC_ID = migration_settings.telegram_logger_topic_id
TELEGRAM_NOTIFY = migration_settings.telegram_notify

WEBHOOK_ADDRESS = migration_settings.webhook_address
WEBHOOK_SECRET = migration_settings.webhook_secret
WEBHOOK_PROXY_URL = migration_settings.webhook_proxy_url

NOTIFICATION_PROXY_URL = migration_settings.notification_proxy_url

# recurrent notifications
RECURRENT_NOTIFICATIONS_TIMEOUT = migration_settings.recurrent_notifications_timeout
NUMBER_OF_RECURRENT_NOTIFICATIONS = migration_settings.number_of_recurrent_notifications

# Notification thresholds
NOTIFY_REACHED_USAGE_PERCENT = migration_settings.notify_reached_usage_percent
NOTIFY_DAYS_LEFT = migration_settings.notify_days_left

# Discord webhook
DISCORD_WEBHOOK_URL = migration_settings.discord_webhook_url

# Subscription settings
XRAY_SUBSCRIPTION_URL_PREFIX = migration_settings.xray_subscription_url_prefix.strip("/")
SUB_UPDATE_INTERVAL = migration_settings.sub_update_interval
SUB_SUPPORT_URL = migration_settings.sub_support_url
SUB_PROFILE_TITLE = migration_settings.sub_profile_title
HOST_STATUS_FILTER = migration_settings.host_status_filter

# Custom JSON settings
USE_CUSTOM_JSON_DEFAULT = migration_settings.use_custom_json_default
USE_CUSTOM_JSON_FOR_V2RAYN = migration_settings.use_custom_json_for_v2rayn
USE_CUSTOM_JSON_FOR_V2RAYNG = migration_settings.use_custom_json_for_v2rayng
USE_CUSTOM_JSON_FOR_STREISAND = migration_settings.use_custom_json_for_streisand
USE_CUSTOM_JSON_FOR_HAPP = migration_settings.use_custom_json_for_happ
USE_CUSTOM_JSON_FOR_NPVTUNNEL = migration_settings.use_custom_json_for_npvtunnel


# Build settings dictionaries
telegram = {
    "enable": True if TELEGRAM_API_TOKEN and TELEGRAM_WEBHOOK_URL and TELEGRAM_WEBHOOK_SECRET_KEY else False,
    "token": TELEGRAM_API_TOKEN if TELEGRAM_API_TOKEN else None,
    "webhook_url": TELEGRAM_WEBHOOK_URL if TELEGRAM_WEBHOOK_URL else None,
    "webhook_secret": TELEGRAM_WEBHOOK_SECRET_KEY if TELEGRAM_WEBHOOK_SECRET_KEY else None,
    "proxy_url": TELEGRAM_PROXY_URL,
}

discord = {"enable": False, "token": None, "proxy_url": None}

webhook = {
    "enable": True if WEBHOOK_ADDRESS else False,
    "webhooks": [{"url": url, "secret": WEBHOOK_SECRET} for url in WEBHOOK_ADDRESS],
    "days_left": NOTIFY_DAYS_LEFT,
    "usage_percent": NOTIFY_REACHED_USAGE_PERCENT,
    "timeout": RECURRENT_NOTIFICATIONS_TIMEOUT,
    "recurrent": NUMBER_OF_RECURRENT_NOTIFICATIONS,
    "proxy_url": WEBHOOK_PROXY_URL,
}

notification_settings = {
    "notify_telegram": TELEGRAM_NOTIFY,
    "notify_discord": True if DISCORD_WEBHOOK_URL else False,
    "telegram_api_token": TELEGRAM_API_TOKEN if TELEGRAM_API_TOKEN else None,
    "telegram_admin_id": TELEGRAM_ADMIN_ID if TELEGRAM_ADMIN_ID else None,
    "telegram_channel_id": TELEGRAM_LOGGER_CHANNEL_ID if TELEGRAM_LOGGER_CHANNEL_ID else None,
    "telegram_topic_id": TELEGRAM_LOGGER_TOPIC_ID if TELEGRAM_LOGGER_TOPIC_ID else None,
    "discord_webhook_url": DISCORD_WEBHOOK_URL if DISCORD_WEBHOOK_URL else None,
    "proxy_url": NOTIFICATION_PROXY_URL,
    "max_retries": 3,
}

notification_enable = {
    "admin": True,
    "core": True,
    "group": True,
    "host": True,
    "login": True,
    "node": True,
    "user": True,
    "user_template": True,
    "days_left": True,
    "percentage_reached": True,
}

xray_rule = ""


def append_rule(pattern: str) -> None:
    global xray_rule
    if xray_rule:
        xray_rule += "|" + pattern
    else:
        xray_rule = pattern


if USE_CUSTOM_JSON_DEFAULT:
    append_rule("[Vv]2rayNG")
    append_rule("[Vv]2rayN")
    append_rule("[Ss]treisand")
    append_rule("[Hh]app")
    append_rule(r"[Kk]tor\-client")

else:
    if USE_CUSTOM_JSON_FOR_V2RAYNG:
        append_rule("[Vv]2rayNG")
    if USE_CUSTOM_JSON_FOR_V2RAYN:
        append_rule("[Vv]2rayN")
    if USE_CUSTOM_JSON_FOR_STREISAND:
        append_rule("[Ss]treisand")
    if USE_CUSTOM_JSON_FOR_HAPP:
        append_rule("[Hh]app")
    if USE_CUSTOM_JSON_FOR_NPVTUNNEL:
        append_rule(r"[Kk]tor\-client")


rules = [
    {
        "pattern": r"^(?:FlClashX?|Flowvy|[Cc]lash(?:-(?:[Vv]erge|nyanpasu)|X [Mm]eta|-?[Mm]eta)|[Kk]oala-[Cc]lash|[Mm](?:urge|ihomo)|prizrak-box|clash\.meta)",
        "target": "clash_meta",
    },
    {"pattern": r"^([Cc]lash|[Ss]tash)", "target": "clash"},
    {"pattern": r"^(SFA|SFI|SFM|SFT|[Kk]aring|[Hh]iddify[Nn]ext)|.*[Ss]ing[\-b]?ox.*", "target": "sing_box"},
    {"pattern": r"^(SS|SSR|SSD|SSS|Outline|Shadowsocks|SSconf)", "target": "outline"},
    {
        "pattern": r"^.*",  # Default catch-all pattern
        "target": "links_base64",
    },
]

if xray_rule:
    rules.insert(-1, {"pattern": r"^(%s)" % xray_rule, "target": "xray"})

manual_sub_request = {
    "links": True,
    "links_base64": True,
    "xray": True,
    "sing_box": True,
    "clash": True,
    "clash_meta": True,
    "outline": True,
}

subscription = {
    "url_prefix": XRAY_SUBSCRIPTION_URL_PREFIX,
    "update_interval": SUB_UPDATE_INTERVAL,
    "support_url": SUB_SUPPORT_URL,
    "profile_title": SUB_PROFILE_TITLE,
    "host_status_filter": HOST_STATUS_FILTER,
    "randomize_order": False,
    "rules": rules,
    "manual_sub_request": manual_sub_request,
}

base_settings = {
    "telegram": telegram,
    "discord": discord,
    "webhook": webhook,
    "notification_settings": notification_settings,
    "notification_enable": notification_enable,
    "subscription": subscription,
}


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram", sa.JSON(), nullable=False),
        sa.Column("discord", sa.JSON(), nullable=False),
        sa.Column("webhook", sa.JSON(), nullable=False),
        sa.Column("notification_settings", sa.JSON(), nullable=False),
        sa.Column("notification_enable", sa.JSON(), nullable=False),
        sa.Column("subscription", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # ### end Alembic commands ###

    op.bulk_insert(
        sa.table(
            "settings",
            sa.Column("id", sa.Integer),
            sa.Column("telegram", sa.JSON),
            sa.Column("discord", sa.JSON),
            sa.Column("webhook", sa.JSON),
            sa.Column("notification_settings", sa.JSON),
            sa.Column("notification_enable", sa.JSON),
            sa.Column("subscription", sa.JSON),
        ),
        [base_settings],
    )


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("settings")
    # ### end Alembic commands ###
