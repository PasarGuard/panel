"""Former env vars that are now panel settings: the readers follow the DB settings, and the migration copies the
old env values of existing installs."""

import importlib.util
import logging
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest

from app import settings as app_settings
from app.jobs import node_checker, node_stats
from app.models.settings import General, Telegram, UsageSettings
from app.routers import system
from app.utils import jwt as jwt_utils

MIGRATION = (
    Path(__file__).resolve().parents[1] / "app/db/migrations/versions/b849540d85bb_move_runtime_env_vars_to_settings.py"
)


@pytest.fixture(scope="module")
def migration():
    spec = importlib.util.spec_from_file_location("move_runtime_env_vars_to_settings", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _serve_general(monkeypatch, module, general: General) -> None:
    async def get_general_settings():
        return general

    monkeypatch.setattr(module, "general_settings", get_general_settings)


def test_migration_reads_environment_before_dotenv_in_any_case(migration):
    values = migration.read_env_values(
        environ={"disable_recording_node_usage": "true", "PATH": "/bin"},
        dotenv={"DISABLE_RECORDING_NODE_USAGE": "false", "Node_Health_Max_Backoff": "0"},
    )

    assert values == {"DISABLE_RECORDING_NODE_USAGE": "true", "NODE_HEALTH_MAX_BACKOFF": "0"}


def test_migration_reads_dotenv_file(migration, tmp_path, monkeypatch):
    (tmp_path / ".env").write_text('# comment\nSTOP_NODES_ON_SHUTDOWN = "False"\nUSER_SUBSCRIPTION_CLIENTS_LIMIT=25\n')
    monkeypatch.chdir(tmp_path)

    assert migration.read_env_values(environ={}) == {
        "STOP_NODES_ON_SHUTDOWN": "False",
        "USER_SUBSCRIPTION_CLIENTS_LIMIT": "25",
    }


def test_migration_copies_set_values_and_leaves_the_rest(migration):
    stored = {
        "general": {"default_method": "aes-128-gcm", "node_health": {"fail_threshold": 4}},
        "subscription": {"url_prefix": "https://sub.example.com", "rules": []},
        "telegram": {"enable": False},
    }
    env = {
        "DISABLE_RECORDING_NODE_USAGE": "TRUE",
        "ENABLE_RECORDING_NODES_STATS": "yes",
        "RESET_USER_USAGE_CLEAN_CHART_DATA": "0",
        "NODE_HEALTH_RECOVER_THRESHOLD": " 5 ",
        "STOP_NODES_ON_SHUTDOWN": "off",
        "JWT_ACCESS_TOKEN_EXPIRE_MINUTES": "0",
        "USER_SUBSCRIPTION_CLIENTS_LIMIT": "-1",
        "DO_NOT_LOG_TELEGRAM_BOT": "false",
    }

    sections = migration.apply_env_values(stored, env)

    assert sections["general"] == {
        "default_method": "aes-128-gcm",
        "usage": {"record_node_usage": False, "record_node_stats": True, "reset_usage_clean_chart_data": False},
        "node_health": {"fail_threshold": 4, "recover_threshold": 5},
        "stop_nodes_on_shutdown": False,
        "admin_token_expire_minutes": 0,
    }
    assert sections["subscription"] == {"url_prefix": "https://sub.example.com", "rules": [], "clients_limit": -1}
    assert sections["telegram"] == {"enable": False, "do_not_log_bot": False}
    # The stored sections are not changed in place
    assert stored["general"] == {"default_method": "aes-128-gcm", "node_health": {"fail_threshold": 4}}
    # Every migrated value fits the settings models
    general = General.model_validate(sections["general"])
    assert general.usage.record_node_usage is False
    assert Telegram.model_validate(sections["telegram"]).do_not_log_bot is False


def test_migration_inverts_disable_recording_node_usage(migration):
    for raw, expected in (("true", False), ("1", False), ("False", True), ("no", True)):
        sections = migration.apply_env_values({}, {"DISABLE_RECORDING_NODE_USAGE": raw})
        assert sections["general"] == {"usage": {"record_node_usage": expected}}


def test_migration_without_env_values_writes_nothing(migration):
    stored = {"general": {"default_method": "aes-128-gcm"}, "subscription": {}, "telegram": {}}

    assert migration.apply_env_values(stored, {}) == stored


def test_migration_skips_values_the_settings_reject(migration, caplog):
    with caplog.at_level(logging.INFO, logger="alembic.runtime.migration"):
        sections = migration.apply_env_values(
            {},
            {
                "NODE_HEALTH_FAIL_THRESHOLD": "0",
                "STOP_NODES_ON_SHUTDOWN": "maybe",
                "NODE_HEALTH_MAX_BACKOFF": "0",
                "JWT_ACCESS_TOKEN_EXPIRE_MINUTES": "5256001",
            },
        )

    assert sections["general"] == {"node_health": {"max_backoff": 0}}
    assert "Skipped NODE_HEALTH_FAIL_THRESHOLD" in caplog.text
    assert "Skipped STOP_NODES_ON_SHUTDOWN" in caplog.text
    assert "Skipped JWT_ACCESS_TOKEN_EXPIRE_MINUTES" in caplog.text
    assert "Moved NODE_HEALTH_MAX_BACKOFF" in caplog.text


def test_migration_downgrade_removes_the_added_keys(migration):
    upgraded = migration.apply_env_values(
        {"general": {"default_method": "aes-128-gcm"}, "subscription": {"rules": []}, "telegram": {"enable": False}},
        {name: "1" for name in migration.ENV_SETTINGS},
    )

    assert migration.remove_added_keys(upgraded) == {
        "general": {"default_method": "aes-128-gcm"},
        "subscription": {"rules": []},
        "telegram": {"enable": False},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(("postgresql", "enabled"), [(True, False), (False, True)])
async def test_node_stats_job_returns_early_when_off(monkeypatch, postgresql, enabled):
    _serve_general(monkeypatch, node_stats, General(usage=UsageSettings(record_node_stats=enabled)))
    monkeypatch.setitem(node_stats.database_settings.__dict__, "is_postgresql", postgresql)
    get_nodes = AsyncMock(return_value=[])
    monkeypatch.setattr(node_stats.node_manager, "get_healthy_nodes", get_nodes)

    await node_stats.gather_nodes_stats()

    get_nodes.assert_not_awaited()


@pytest.mark.asyncio
async def test_node_stats_job_runs_when_on(monkeypatch):
    _serve_general(monkeypatch, node_stats, General(usage=UsageSettings(record_node_stats=True)))
    monkeypatch.setitem(node_stats.database_settings.__dict__, "is_postgresql", True)
    get_nodes = AsyncMock(return_value=[])
    monkeypatch.setattr(node_stats.node_manager, "get_healthy_nodes", get_nodes)

    await node_stats.gather_nodes_stats()

    get_nodes.assert_awaited_once()


async def _fail_general_settings():
    raise RuntimeError("settings unavailable")


@pytest.mark.asyncio
async def test_shutdown_leaves_nodes_running_when_the_setting_fails_to_load(monkeypatch):
    monkeypatch.setattr(node_checker, "general_settings", _fail_general_settings)
    monkeypatch.setattr(node_checker, "is_multi_worker", lambda: False)
    get_nodes = AsyncMock(return_value={})
    monkeypatch.setattr(node_checker.node_manager, "get_nodes", get_nodes)

    await node_checker.shutdown_nodes()

    get_nodes.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("stop", "stops"), [(True, True), (False, False)])
async def test_shutdown_follows_the_stop_nodes_setting(monkeypatch, stop, stops):
    _serve_general(monkeypatch, node_checker, General(stop_nodes_on_shutdown=stop))
    monkeypatch.setattr(node_checker, "is_multi_worker", lambda: False)
    get_nodes = AsyncMock(return_value={})
    monkeypatch.setattr(node_checker.node_manager, "get_nodes", get_nodes)

    await node_checker.shutdown_nodes()

    assert get_nodes.await_count == (1 if stops else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("minutes", [30, 0, -5])
async def test_admin_token_expiry_follows_the_setting(monkeypatch, minutes):
    _serve_general(monkeypatch, jwt_utils, General(admin_token_expire_minutes=minutes))
    monkeypatch.setattr(jwt_utils, "get_secret_key", AsyncMock(return_value="secret"))

    token = await jwt_utils.create_admin_token(None, "admin")

    payload = jwt.decode(token, "secret", algorithms=["HS256"], options={"verify_exp": False})
    if minutes > 0:
        expires_in = payload["exp"] - datetime.now(UTC).timestamp()
        assert minutes * 60 - 30 < expires_in <= minutes * 60
    else:
        assert "exp" not in payload


def _access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4", "POST", path, "1.1", 200),
        None,
    )


def test_telegram_webhook_log_filter_follows_the_setting(monkeypatch):
    webhook = f"{system.router.prefix}{system.TELEGRAM_WEBHOOK_PATH}"
    log_filter = next(
        f for f in logging.getLogger("uvicorn.access").filters if isinstance(f, system.TelegramWebhookLogFilter)
    )

    monkeypatch.setattr(app_settings, "_do_not_log_telegram_bot", True)
    assert log_filter.filter(_access_record(webhook)) is False
    assert log_filter.filter(_access_record("/api/system")) is True

    monkeypatch.setattr(app_settings, "_do_not_log_telegram_bot", False)
    assert log_filter.filter(_access_record(webhook)) is True


@pytest.mark.asyncio
async def test_loading_telegram_settings_updates_the_log_flag(monkeypatch):
    row = SimpleNamespace(telegram={"enable": False, "do_not_log_bot": False})

    class _GetDB:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(app_settings, "GetDB", _GetDB)
    monkeypatch.setattr(app_settings, "get_settings", AsyncMock(return_value=row))
    monkeypatch.setattr(app_settings, "_do_not_log_telegram_bot", True)
    await app_settings.telegram_settings.cache.clear()
    try:
        await app_settings.telegram_settings()
        assert app_settings.do_not_log_telegram_bot() is False

        row.telegram = {"enable": False}
        await app_settings.telegram_settings.cache.clear()
        await app_settings.telegram_settings()
        assert app_settings.do_not_log_telegram_bot() is True
    finally:
        await app_settings.telegram_settings.cache.clear()
