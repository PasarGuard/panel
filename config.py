from decouple import config
from dotenv import load_dotenv

TESTING = config("TESTING", default=False, cast=bool)
if not TESTING:
    load_dotenv()
    # Reload TESTING in case it is defined in .env
    TESTING = config("TESTING", default=TESTING, cast=bool)

SQLALCHEMY_DATABASE_URL = config("SQLALCHEMY_DATABASE_URL", default="sqlite+aiosqlite:///db.sqlite3")
SQLALCHEMY_POOL_SIZE = config("SQLALCHEMY_POOL_SIZE", cast=int, default=25)
SQLALCHEMY_MAX_OVERFLOW = config("SQLALCHEMY_MAX_OVERFLOW", cast=int, default=60)
ECHO_SQL_QUERIES = config("ECHO_SQL_QUERIES", cast=bool, default=False)

UVICORN_HOST = config("UVICORN_HOST", default="0.0.0.0")
UVICORN_PORT = config("UVICORN_PORT", cast=int, default=8000)
UVICORN_UDS = config("UVICORN_UDS", default=None)
UVICORN_SSL_CERTFILE = config("UVICORN_SSL_CERTFILE", default=None)
UVICORN_SSL_KEYFILE = config("UVICORN_SSL_KEYFILE", default=None)
UVICORN_SSL_CA_TYPE = config("UVICORN_SSL_CA_TYPE", default="public").lower()
UVICORN_WORKERS = config("UVICORN_WORKERS", default=1, cast=int)
DASHBOARD_PATH = config("DASHBOARD_PATH", default="/dashboard/")
UVICORN_LOOP = config("UVICORN_LOOP", default="auto", cast=str)
RUN_SCHEDULER = config("RUN_SCHEDULER", default=False, cast=bool)
NODE_ROLE = config("NODE_ROLE", default="panel").strip().lower()
IS_NODE_WORKER = NODE_ROLE == "node-worker"

_RAW_MULTI_WORKER = config("MULTI_WORKER", default=None)
if _RAW_MULTI_WORKER is None:
    MULTI_WORKER = UVICORN_WORKERS > 1
else:
    MULTI_WORKER = str(_RAW_MULTI_WORKER).lower() in ("1", "true", "yes", "y", "on")

REDIS_ENABLED = config("REDIS_ENABLED", default=False, cast=bool)
REDIS_HOST = config("REDIS_HOST", default="localhost")
REDIS_PORT = config("REDIS_PORT", cast=int, default=6379)
REDIS_DB = config("REDIS_DB", cast=int, default=0)

NATS_ENABLED = config("NATS_ENABLED", default=False, cast=bool)
NATS_URL = config("NATS_URL", default="nats://localhost:4222")
NATS_WORKER_SYNC_SUBJECT = config("NATS_WORKER_SYNC_SUBJECT", default="pasarguard.worker_sync")
NATS_NODE_COMMAND_SUBJECT = config("NATS_NODE_COMMAND_SUBJECT", default="pasarguard.node.command")
NATS_NODE_RPC_SUBJECT = config("NATS_NODE_RPC_SUBJECT", default="pasarguard.node.rpc")
NATS_NODE_LOG_SUBJECT = config("NATS_NODE_LOG_SUBJECT", default="pasarguard.node.logs")
NATS_NODE_RPC_TIMEOUT = config("NATS_NODE_RPC_TIMEOUT", cast=float, default=30.0)
CORE_PUBSUB_CHANNEL = config("CORE_PUBSUB_CHANNEL", default="core_hosts_updates")
HOST_PUBSUB_CHANNEL = config("HOST_PUBSUB_CHANNEL", default="host_manager_updates")

DEBUG = config("DEBUG", default=False, cast=bool)
DOCS = config("DOCS", default=False, cast=bool)

ALLOWED_ORIGINS = config("ALLOWED_ORIGINS", default="*").split(",")

VITE_BASE_API = (
    f"{'https' if UVICORN_SSL_CERTFILE and UVICORN_SSL_KEYFILE else 'http'}://127.0.0.1:{UVICORN_PORT}/"
    if DEBUG and config("VITE_BASE_API", default="/") == "/"
    else config("VITE_BASE_API", default="/")
)

# For backward compatibility
SUBSCRIPTION_PATH = config("XRAY_SUBSCRIPTION_PATH", default="").strip("/")
if not SUBSCRIPTION_PATH:
    SUBSCRIPTION_PATH = config("SUBSCRIPTION_PATH", default="sub").strip("/")

USER_SUBSCRIPTION_CLIENTS_LIMIT = config("USER_SUBSCRIPTION_CLIENTS_LIMIT", cast=int, default=10)

JWT_ACCESS_TOKEN_EXPIRE_MINUTES = config("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", cast=int, default=1440)

CUSTOM_TEMPLATES_DIRECTORY = config("CUSTOM_TEMPLATES_DIRECTORY", default=None)
SUBSCRIPTION_PAGE_TEMPLATE = config("SUBSCRIPTION_PAGE_TEMPLATE", default="subscription/index.html")
HOME_PAGE_TEMPLATE = config("HOME_PAGE_TEMPLATE", default="home/index.html")

CLASH_SUBSCRIPTION_TEMPLATE = config("CLASH_SUBSCRIPTION_TEMPLATE", default="clash/default.yml")

SINGBOX_SUBSCRIPTION_TEMPLATE = config("SINGBOX_SUBSCRIPTION_TEMPLATE", default="singbox/default.json")

XRAY_SUBSCRIPTION_TEMPLATE = config("XRAY_SUBSCRIPTION_TEMPLATE", default="xray/default.json")

USER_AGENT_TEMPLATE = config("USER_AGENT_TEMPLATE", default="user_agent/default.json")
GRPC_USER_AGENT_TEMPLATE = config("GRPC_USER_AGENT_TEMPLATE", default="user_agent/grpc.json")

EXTERNAL_CONFIG = config("EXTERNAL_CONFIG", default="", cast=str)

USERS_AUTODELETE_DAYS = config("USERS_AUTODELETE_DAYS", default=-1, cast=int)
USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS = config("USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS", default=False, cast=bool)

DO_NOT_LOG_TELEGRAM_BOT = config("DO_NOT_LOG_TELEGRAM_BOT", default=True, cast=bool)

SAVE_LOGS_TO_FILE = config("SAVE_LOGS_TO_FILE", default=False, cast=bool)
LOG_FILE_PATH = config("LOG_FILE_PATH", default="pasarguard.log")
LOG_BACKUP_COUNT = config("LOG_BACKUP_COUNT", cast=int, default=72)
LOG_ROTATION_ENABLED = config("LOG_ROTATION_ENABLED", default=False, cast=bool)
LOG_ROTATION_INTERVAL = config("LOG_ROTATION_INTERVAL", cast=int, default=1)
LOG_ROTATION_UNIT = config("LOG_ROTATION_UNIT", default="H")
LOG_MAX_BYTES = config("LOG_MAX_BYTES", cast=int, default=10485760)  # default: 10 MB
VALID_LOG_LEVELS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")
LOG_LEVEL = config("LOG_LEVEL", default="INFO").upper()
if LOG_LEVEL not in VALID_LOG_LEVELS:
    LOG_LEVEL = "INFO"

# USERNAME: PASSWORD
SUDOERS = (
    {config("SUDO_USERNAME"): config("SUDO_PASSWORD")}
    if config("SUDO_USERNAME", default="") and config("SUDO_PASSWORD", default="")
    else {}
)

DISABLE_RECORDING_NODE_USAGE = config("DISABLE_RECORDING_NODE_USAGE", cast=bool, default=False)

# due to high amount of data this job is only available for postgresql and timescaledb
if SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
    ENABLE_RECORDING_NODES_STATS = config("ENABLE_RECORDING_NODES_STATS", cast=bool, default=False)
else:
    ENABLE_RECORDING_NODES_STATS = False

# Interval jobs, all values are in seconds
JOB_CORE_HEALTH_CHECK_INTERVAL = config("JOB_CORE_HEALTH_CHECK_INTERVAL", cast=int, default=10)
JOB_RECORD_NODE_USAGES_INTERVAL = config("JOB_RECORD_NODE_USAGES_INTERVAL", cast=int, default=30)
JOB_RECORD_USER_USAGES_INTERVAL = config("JOB_RECORD_USER_USAGES_INTERVAL", cast=int, default=10)
JOB_REVIEW_USERS_INTERVAL = config("JOB_REVIEW_USERS_INTERVAL", cast=int, default=30)
JOB_SEND_NOTIFICATIONS_INTERVAL = config("JOB_SEND_NOTIFICATIONS_INTERVAL", cast=int, default=30)
JOB_GATHER_NODES_STATS_INTERVAL = config("JOB_GATHER_NODES_STATS_INTERVAL", cast=int, default=25)
JOB_REMOVE_OLD_INBOUNDS_INTERVAL = config("JOB_REMOVE_OLD_INBOUNDS_INTERVAL", cast=int, default=600)
JOB_REMOVE_EXPIRED_USERS_INTERVAL = config("JOB_REMOVE_EXPIRED_USERS_INTERVAL", cast=int, default=3600)
JOB_RESET_USER_DATA_USAGE_INTERVAL = config("JOB_RESET_USER_DATA_USAGE_INTERVAL", cast=int, default=600)
JOB_RESET_NODE_USAGE_INTERVAL = config("JOB_RESET_NODE_USAGE_INTERVAL", cast=int, default=60)
JOB_CHECK_NODE_LIMITS_INTERVAL = config("JOB_CHECK_NODE_LIMITS_INTERVAL", cast=int, default=60)
JOB_CLEANUP_SUBSCRIPTION_UPDATES_INTERVAL = config("JOB_CLEANUP_SUBSCRIPTION_UPDATES_INTERVAL", cast=int, default=600)
