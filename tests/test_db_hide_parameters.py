import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import build_engine_options
from config import database_settings

SECRET = "never-log-this-password-7f3a"


@pytest.mark.asyncio
async def test_a_failed_statement_does_not_carry_its_bind_values_into_the_error():
    options = build_engine_options(database_settings)
    options.pop("connect_args", None)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", **options)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE secrets (value TEXT NOT NULL UNIQUE)"))
            await conn.execute(text("INSERT INTO secrets (value) VALUES (:value)"), {"value": SECRET})
            with pytest.raises(IntegrityError) as raised:
                await conn.execute(text("INSERT INTO secrets (value) VALUES (:value)"), {"value": SECRET})
    finally:
        await engine.dispose()

    assert SECRET not in str(raised.value)
