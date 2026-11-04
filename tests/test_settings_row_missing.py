import logging
import shutil
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.command import upgrade
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import settings as app_settings
from app.db import base

ROOT = Path(__file__).resolve().parents[1]

ACCESSORS = [
    "telegram_settings",
    "webhook_settings",
    "notification_settings",
    "notification_enable",
    "subscription_settings",
    "hwid_settings",
    "general_settings",
    "cleanup_settings",
]


def _migrate_to_head(path: Path) -> None:
    url = f"sqlite:///{path}"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "app/db/migrations"))
    config.set_main_option("sqlalchemy.url", url)
    logger_states = {
        logger: logger.disabled
        for logger in logging.root.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    }
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            upgrade(config, "head")
    finally:
        engine.dispose()
        for logger, disabled in logger_states.items():
            logger.disabled = disabled


def _execute(path: Path, *statements: str) -> list:
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.begin() as connection:
            results = [connection.execute(text(statement)) for statement in statements]
            return [row for row in results[-1]] if results[-1].returns_rows else []
    finally:
        engine.dispose()


def _settings_rows(path: Path) -> int:
    return _execute(path, "SELECT COUNT(*) FROM settings")[0][0]


@pytest.fixture(scope="module")
def database_at_head(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("settings-row") / "head.db"
    _migrate_to_head(path)
    return path


@pytest.fixture
def database_without_the_row(database_at_head: Path, tmp_path: Path) -> Path:
    path = tmp_path / "panel.db"
    shutil.copyfile(database_at_head, path)
    _execute(path, "DELETE FROM settings")
    assert _settings_rows(path) == 0
    return path


@pytest_asyncio.fixture(loop_scope="function")
async def panel_reads(database_without_the_row: Path, monkeypatch: pytest.MonkeyPatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_without_the_row}")
    monkeypatch.setattr(
        base,
        "SessionLocal",
        async_sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine),
    )
    for accessor in ACCESSORS:
        await getattr(app_settings, accessor).cache.clear()
    try:
        yield database_without_the_row
    finally:
        for accessor in ACCESSORS:
            await getattr(app_settings, accessor).cache.clear()
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("accessor", ACCESSORS)
async def test_every_accessor_reports_the_missing_settings_row_and_how_to_restore_it(accessor: str, panel_reads: Path):
    with pytest.raises(RuntimeError) as raised:
        await getattr(app_settings, accessor)()

    message = str(raised.value)
    assert "9af04c077ede" in message
    assert "does not bring it back" in message
    assert "backup" in message
    assert "new database" in message


def test_running_the_migrations_again_does_not_bring_the_row_back(database_without_the_row: Path):
    _migrate_to_head(database_without_the_row)

    assert _settings_rows(database_without_the_row) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["backup", "new database"])
async def test_copying_the_row_from_a_backup_or_a_new_database_restores_every_accessor(
    source: str, database_at_head: Path, panel_reads: Path, tmp_path: Path
):
    copy_from = tmp_path / "source.db"
    if source == "backup":
        shutil.copyfile(database_at_head, copy_from)
    else:
        _migrate_to_head(copy_from)

    _execute(
        panel_reads,
        f"ATTACH DATABASE '{copy_from}' AS source",
        "INSERT INTO settings SELECT * FROM source.settings",
    )

    for accessor in ACCESSORS:
        assert await getattr(app_settings, accessor)() is not None
