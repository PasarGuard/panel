import os
import subprocess
import sys
from pathlib import Path


def test_migrations_run_with_percent_in_database_url(tmp_path: Path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'pg%25test.sqlite3').as_posix()}"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
        env={**os.environ, "SQLALCHEMY_DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.glob("*.sqlite3"))
