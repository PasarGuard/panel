"""Real migrations, owner creation and production authentication in an isolated DB."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_real_database_is_private_and_never_resets_owner(tmp_path):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'railway.sqlite3'}"
    env = dict(
        os.environ,
        SQLALCHEMY_DATABASE_URL=database_url,
        DATABASE_URL=database_url,
        DEBUG="false",
        TESTING="false",
        NATS_ENABLED="false",
    )
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    assert migration.returncode == 0, migration.stderr
    script = r"""
import asyncio
import json
from pathlib import Path
from sqlalchemy import select, func
from app.db import GetDB
from app.db.models import Admin
from app.db.crud.admin import get_owner, update_owner_password
from app.routers.authentication import validate_admin
from cli.railway import bootstrap_owner
from config import runtime_settings
from railway_runtime import CREDENTIALS_FILE

async def run():
    directory = Path(__import__('sys').argv[1])
    assert runtime_settings.debug is False
    assert await bootstrap_owner(directory) is True
    credentials = json.loads((directory / CREDENTIALS_FILE).read_text())
    async with GetDB() as db:
        admin = await validate_admin(db, credentials['username'], credentials['password'])
        assert admin is not None and admin.id is not None
        owner = await get_owner(db)
        assert owner.role_id == 1
        await update_owner_password(db, owner, 'ChangedAaBb12!private-secret')
    assert await bootstrap_owner(directory) is False
    async with GetDB() as db:
        assert await validate_admin(db, 'owner', credentials['password']) is None
        assert await validate_admin(db, 'owner', 'ChangedAaBb12!private-secret') is not None
        assert (await db.execute(select(func.count(Admin.id)))).scalar_one() == 1
    (directory / CREDENTIALS_FILE).unlink()
    assert await bootstrap_owner(directory) is False
    assert not (directory / CREDENTIALS_FILE).exists()
    print('Real production owner bootstrap, password preservation and deletion checks passed')

asyncio.run(run())
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "private")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    # Never include generated credentials in assertion diagnostics.
    assert result.returncode == 0, (
        f"Owner integration failed (exit {result.returncode}); see isolated test configuration"
    )
    assert "checks passed" in result.stdout
    assert 'password"' not in result.stdout + result.stderr
