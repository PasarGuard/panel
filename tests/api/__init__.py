import asyncio
import json

from decouple import config
from fastapi.testclient import TestClient

from sqlalchemy.exc import SQLAlchemyError
from app.db import base
from app.db.base import SessionLocal as TestSession

from .helpers import create_admin, unique_name

XRAY_JSON_TEST_FILE = "tests/api/xray_config-test.json"

TEST_FROM = config("TEST_FROM", default="local")
DATABASE_URL = "sqlite+aiosqlite://?cache=shared"
print(f"TEST_FROM: {TEST_FROM}")
print(f"DATABASE_URL: {DATABASE_URL}")


async def create_tables():
    from app.db import base
    from app.db.models import Admin  # noqa

    async with base.engine.begin() as conn:
        await conn.run_sync(base.Base.metadata.create_all)


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


from app import app  # noqa


app.dependency_overrides[base.get_db] = get_test_db

if TEST_FROM == "local":
    import app.db.models as _models # noqa
    print(f"Metadata tables: {base.Base.metadata.tables.keys()}")
    asyncio.run(create_tables())


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
