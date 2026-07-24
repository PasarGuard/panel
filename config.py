from functools import cached_property
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from role import Role


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class RuntimeSettings(EnvSettings):
    testing: bool = Field(default=False, validation_alias="TESTING")
    debug: bool = Field(default=False, validation_alias="DEBUG")
    docs: bool = Field(default=False, validation_alias="DOCS")
    role: Role = Field(default=Role.ALL_IN_ONE, validation_alias="ROLE")

    @field_validator("role", mode="before")
    @classmethod
    def parse_role(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip().lower()
        return value


runtime_settings = RuntimeSettings()


class DatabaseSettings(EnvSettings):
    url: str = Field(default="sqlite+aiosqlite:///db.sqlite3", validation_alias="SQLALCHEMY_DATABASE_URL")
    pool_size: int = Field(default=25, validation_alias="SQLALCHEMY_POOL_SIZE")
    max_overflow: int = Field(default=60, validation_alias="SQLALCHEMY_MAX_OVERFLOW")
    pool_recycle: int = Field(default=300, validation_alias="SQLALCHEMY_POOL_RECYCLE")
    connect_timeout: int = Field(default=5, gt=0, validation_alias="SQLALCHEMY_CONNECT_TIMEOUT")
    echo_queries: bool = Field(default=False, validation_alias="ECHO_SQL_QUERIES")

    @cached_property
    def is_postgresql(self) -> bool:
        return self.url.startswith("postgresql")

    @cached_property
    def is_mysql(self) -> bool:
        return self.url.startswith(("mysql", "mariadb"))

    @cached_property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")


class ServerSettings(EnvSettings):
    host: str = Field(default="0.0.0.0", validation_alias="UVICORN_HOST")
    port: int = Field(default=8000, validation_alias="UVICORN_PORT")
    uds: str | None = Field(default=None, validation_alias="UVICORN_UDS")
    ssl_certfile: str | None = Field(default=None, validation_alias="UVICORN_SSL_CERTFILE")
    ssl_keyfile: str | None = Field(default=None, validation_alias="UVICORN_SSL_KEYFILE")
    ssl_ca_type: str = Field(default="public", validation_alias="UVICORN_SSL_CA_TYPE")
    workers: int = Field(default=1, validation_alias="UVICORN_WORKERS")
    loop: str = Field(default="auto", validation_alias="UVICORN_LOOP")
    proxy_headers: bool = Field(default=False, validation_alias="UVICORN_PROXY_HEADERS")
    forwarded_allow_ips: str | list[str] = Field(default="127.0.0.1", validation_alias="UVICORN_FORWARDED_ALLOW_IPS")

    @field_validator("ssl_ca_type")
    @classmethod
    def normalize_ssl_ca_type(cls, value: str) -> str:
        return value.lower()

    @cached_property
    def has_ssl(self) -> bool:
        return bool(self.ssl_certfile and self.ssl_keyfile)


class DashboardSettings(EnvSettings):
    path: str = Field(default="/dashboard/", validation_alias="DASHBOARD_PATH")
    vite_base_api: str = Field(default="/", validation_alias="VITE_BASE_API")


class NatsSettings(EnvSettings):
    enabled: bool = Field(default=False, validation_alias="NATS_ENABLED")
    url: str = Field(default="nats://localhost:4222", validation_alias="NATS_URL")
    worker_sync_subject: str = Field(default="pasarguard.worker_sync", validation_alias="NATS_WORKER_SYNC_SUBJECT")
    node_command_subject: str = Field(default="pasarguard.node.command", validation_alias="NATS_NODE_COMMAND_SUBJECT")
    node_rpc_subject: str = Field(default="pasarguard.node.rpc", validation_alias="NATS_NODE_RPC_SUBJECT")
    scheduler_rpc_subject: str = Field(
        default="pasarguard.scheduler.rpc", validation_alias="NATS_SCHEDULER_RPC_SUBJECT"
    )
    node_log_subject: str = Field(default="pasarguard.node.logs", validation_alias="NATS_NODE_LOG_SUBJECT")
    node_rpc_timeout: float = Field(default=30.0, validation_alias="NATS_NODE_RPC_TIMEOUT")
    scheduler_rpc_timeout: float = Field(default=5.0, validation_alias="NATS_SCHEDULER_RPC_TIMEOUT")
    node_command_max_payload_bytes: int = Field(default=900000, validation_alias="NATS_NODE_COMMAND_MAX_PAYLOAD_BYTES")
    node_update_users_batch_size: int = Field(default=100, validation_alias="NATS_NODE_UPDATE_USERS_BATCH_SIZE")
    core_pubsub_channel: str = Field(default="core_hosts_updates", validation_alias="CORE_PUBSUB_CHANNEL")
    host_pubsub_channel: str = Field(default="host_manager_updates", validation_alias="HOST_PUBSUB_CHANNEL")
    telegram_kv_bucket: str = Field(default="pasarguard_telegram", validation_alias="NATS_TELEGRAM_KV_BUCKET")
    notification_stream: str = Field(default="NOTIFICATIONS", validation_alias="NATS_NOTIFICATION_STREAM")
    notification_subject: str = Field(default="notifications.queue", validation_alias="NATS_NOTIFICATION_SUBJECT")
    notification_consumer: str = Field(default="notification_workers", validation_alias="NATS_NOTIFICATION_CONSUMER")
    webhook_stream: str = Field(default="WEBHOOK_NOTIFICATIONS", validation_alias="NATS_WEBHOOK_STREAM")
    webhook_subject: str = Field(default="notifications.webhook", validation_alias="NATS_WEBHOOK_SUBJECT")
    webhook_consumer: str = Field(default="webhook_workers", validation_alias="NATS_WEBHOOK_CONSUMER")


class CorsSettings(EnvSettings):
    allowed_origins_raw: str = Field(default="*", validation_alias="ALLOWED_ORIGINS")

    @cached_property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins_raw.split(",") if origin.strip()]


class SubscriptionEnvSettings(EnvSettings):
    xray_path: str = Field(default="", validation_alias="XRAY_SUBSCRIPTION_PATH")
    fallback_path: str = Field(default="sub", validation_alias="SUBSCRIPTION_PATH")
    clients_limit: int = Field(default=10, validation_alias="USER_SUBSCRIPTION_CLIENTS_LIMIT")
    external_config: str = Field(default="", validation_alias="EXTERNAL_CONFIG")

    @cached_property
    def path(self) -> str:
        return (self.xray_path or self.fallback_path).strip("/")


class JwtSettings(EnvSettings):
    access_token_expire_minutes: int = Field(default=1440, validation_alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")


class TemplateSettings(EnvSettings):
    custom_templates_directory: str | None = Field(default=None, validation_alias="CUSTOM_TEMPLATES_DIRECTORY")
    subscription_page_template: str = Field(
        default="subscription/index.html", validation_alias="SUBSCRIPTION_PAGE_TEMPLATE"
    )
    home_page_template: str = Field(default="home/index.html", validation_alias="HOME_PAGE_TEMPLATE")


class UserCleanupSettings(EnvSettings):
    autodelete_days: int = Field(default=-1, validation_alias="USERS_AUTODELETE_DAYS")
    include_limited_accounts: bool = Field(default=False, validation_alias="USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS")


class TelegramEnvSettings(EnvSettings):
    do_not_log_bot: bool = Field(default=True, validation_alias="DO_NOT_LOG_TELEGRAM_BOT")


class LoggingSettings(EnvSettings):
    save_to_file: bool = Field(default=False, validation_alias="SAVE_LOGS_TO_FILE")
    file_path: str = Field(default="pasarguard.log", validation_alias="LOG_FILE_PATH")
    backup_count: int = Field(default=72, validation_alias="LOG_BACKUP_COUNT")
    rotation_enabled: bool = Field(default=False, validation_alias="LOG_ROTATION_ENABLED")
    rotation_interval: int = Field(default=1, validation_alias="LOG_ROTATION_INTERVAL")
    rotation_unit: str = Field(default="H", validation_alias="LOG_ROTATION_UNIT")
    max_bytes: int = Field(default=10485760, validation_alias="LOG_MAX_BYTES")
    level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    @field_validator("level")
    @classmethod
    def normalize_level(cls, value: str) -> str:
        value = value.upper()
        return value if value in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG") else "INFO"


class AuthSettings(EnvSettings):
    sudo_username: str = Field(default="", validation_alias="SUDO_USERNAME")
    sudo_password: str = Field(default="", validation_alias="SUDO_PASSWORD")
    sudoers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def build_sudoers(self) -> AuthSettings:
        if self.sudo_username and self.sudo_password and not self.sudoers:
            self.sudoers[self.sudo_username] = self.sudo_password
        return self


class UsageSettings(EnvSettings):
    disable_recording_node_usage: bool = Field(default=False, validation_alias="DISABLE_RECORDING_NODE_USAGE")
    enable_recording_nodes_stats: bool = Field(default=False, validation_alias="ENABLE_RECORDING_NODES_STATS")
    reset_user_usage_clean_chart_data: bool = Field(
        default=False,
        validation_alias="RESET_USER_USAGE_CLEAN_CHART_DATA",
    )


class JobSettings(EnvSettings):
    core_health_check_interval: int = Field(default=10, validation_alias="JOB_CORE_HEALTH_CHECK_INTERVAL")
    record_node_usages_interval: int = Field(default=30, validation_alias="JOB_RECORD_NODE_USAGES_INTERVAL")
    record_user_usages_interval: int = Field(default=10, validation_alias="JOB_RECORD_USER_USAGES_INTERVAL")
    review_users_interval: int = Field(default=30, validation_alias="JOB_REVIEW_USERS_INTERVAL")
    review_admin_limits_interval: int = Field(default=10, validation_alias="JOB_REVIEW_ADMIN_LIMITS_INTERVAL")
    send_notifications_interval: int = Field(default=30, validation_alias="JOB_SEND_NOTIFICATIONS_INTERVAL")
    gather_nodes_stats_interval: int = Field(default=25, validation_alias="JOB_GATHER_NODES_STATS_INTERVAL")
    remove_old_inbounds_interval: int = Field(default=600, validation_alias="JOB_REMOVE_OLD_INBOUNDS_INTERVAL")
    remove_expired_users_interval: int = Field(default=3600, validation_alias="JOB_REMOVE_EXPIRED_USERS_INTERVAL")
    reset_user_data_usage_interval: int = Field(default=600, validation_alias="JOB_RESET_USER_DATA_USAGE_INTERVAL")
    reset_node_usage_interval: int = Field(default=60, validation_alias="JOB_RESET_NODE_USAGE_INTERVAL")
    check_node_limits_interval: int = Field(default=60, validation_alias="JOB_CHECK_NODE_LIMITS_INTERVAL")
    cleanup_subscription_updates_interval: int = Field(
        default=600, validation_alias="JOB_CLEANUP_SUBSCRIPTION_UPDATES_INTERVAL"
    )


class FeatureSettings(EnvSettings):
    stop_nodes_on_shutdown: bool = Field(default=True, validation_alias="STOP_NODES_ON_SHUTDOWN")


database_settings = DatabaseSettings()
server_settings = ServerSettings()
dashboard_settings = DashboardSettings()
nats_settings = NatsSettings()
cors_settings = CorsSettings()
subscription_env_settings = SubscriptionEnvSettings()
jwt_settings = JwtSettings()
template_settings = TemplateSettings()
user_cleanup_settings = UserCleanupSettings()
telegram_env_settings = TelegramEnvSettings()
logging_settings = LoggingSettings()
auth_settings = AuthSettings()
usage_settings = UsageSettings()
job_settings = JobSettings()
feature_settings = FeatureSettings()

if not database_settings.is_postgresql:
    usage_settings.enable_recording_nodes_stats = False

if runtime_settings.debug and dashboard_settings.vite_base_api == "/":
    scheme = "https" if server_settings.has_ssl else "http"
    dashboard_settings.vite_base_api = f"{scheme}://127.0.0.1:{server_settings.port}/"
