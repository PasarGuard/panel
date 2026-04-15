import asyncio
import json

from alembic.command import upgrade
from alembic.config import Config
from decouple import config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.db import base
from config import SQLALCHEMY_DATABASE_URL

XRAY_JSON_TEST_FILE = "tests/api/xray_config-test.json"

TEST_FROM = config("TEST_FROM", default="local")
# In local mode, use in-memory SQLite by default, but allow override via DATABASE_URL env var
if TEST_FROM == "local":
    # DATABASE_URL = config("DATABASE_URL", default="sqlite+aiosqlite:///:memory:")
    DATABASE_URL = config("DATABASE_URL", default="sqlite+aiosqlite:///./test.db")

else:
    DATABASE_URL = SQLALCHEMY_DATABASE_URL
print(f"TEST_FROM: {TEST_FROM}")
print(f"DATABASE_URL: {DATABASE_URL}")

IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    engine = create_async_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False, "uri": True},
        poolclass=StaticPool,
        # echo=True,
    )
else:
    engine = create_async_engine(
        DATABASE_URL,
        poolclass=NullPool,  # Important for tests
        # echo=True,  # For debugging
    )
TestSession = async_sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)


def run_migrations_sync():
    """Run Alembic migrations synchronously."""
    try:
        # For in-memory SQLite, migrations won't work because each connection gets its own DB
        # So we skip migrations for in-memory and use create_tables instead
        if IS_SQLITE and DATABASE_URL == "sqlite+aiosqlite:///:memory:":
            print("[migrations] Skipping migrations for in-memory SQLite (will use create_tables fallback)")
            return False  # Skip migrations for in-memory SQLite

        # Use a synchronous connection for Alembic; the project env.py supports both.
        sync_db_url = DATABASE_URL
        if "sqlite+aiosqlite" in sync_db_url:
            sync_db_url = sync_db_url.replace("sqlite+aiosqlite", "sqlite")
        elif "postgresql+asyncpg" in sync_db_url:
            sync_db_url = sync_db_url.replace("postgresql+asyncpg", "postgresql")
        elif "mysql+asyncmy" in sync_db_url:
            sync_db_url = sync_db_url.replace("mysql+asyncmy", "mysql+pymysql")

        print(f"[migrations] Running migrations with database: {sync_db_url}")

        # Alembic configuration
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", sync_db_url)

        with create_engine(sync_db_url).begin() as connection:
            alembic_cfg.attributes["connection"] = connection
            upgrade(alembic_cfg, "head")
        print("[migrations] Migrations completed successfully")
        return True  # Migrations ran successfully
    except Exception as e:
        print(f"[migrations] Error running migrations: {e}", file=__import__("sys").stderr)
        raise


def run_migrations():
    """Run Alembic migrations, with fallback to create_tables for in-memory SQLite."""
    migrations_ran = run_migrations_sync()
    if not migrations_ran:
        asyncio.run(create_tables())


async def create_tables():
    """Create tables using SQLAlchemy metadata (fallback method)."""
    async with engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.create_all)


if TEST_FROM == "local":
    run_migrations()


class GetTestDB:
    def __init__(self):
        self.db = TestSession()

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc_value, traceback):
        if isinstance(exc_value, SQLAlchemyError):
            await self.db.rollback()  # rollback on exception

        await self.db.close()


async def get_test_db():
    async with GetTestDB() as db:
        yield db


from app import create_app  # noqa


app = create_app()


app.dependency_overrides[base.get_db] = get_test_db


with open(XRAY_JSON_TEST_FILE, "w") as f:
    f.write(
        json.dumps(
            {
                "log": {"loglevel": "warning"},
                "routing": {"rules": [{"ip": ["geoip:private"], "outboundTag": "BLOCK", "type": "field"}]},
                "inbounds": [
                    {
                        "tag": "Shadowsocks TCP",
                        "listen": "0.0.0.0",
                        "port": 1080,
                        "protocol": "shadowsocks",
                        "settings": {"clients": [], "network": "tcp,udp"},
                    }
                ],
                "outbounds": [{"protocol": "freedom", "tag": "DIRECT"}, {"protocol": "blackhole", "tag": "BLOCK"}],
            },
            indent=4,
        )
    )


client = TestClient(app)
