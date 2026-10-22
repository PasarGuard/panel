"""Exercise dotenv healthchecks using the real settings parser in an isolated directory."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_healthcheck(tmp_path, dotenv):
    for name in ("config.py", "role.py", "healthcheck.sh"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    (tmp_path / ".env").write_text(dotenv)
    python = tmp_path / "python"
    python.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    python.chmod(0o755)
    curl = tmp_path / "curl"
    curl.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    curl.chmod(0o755)
    return subprocess.run(
        ["bash", str(tmp_path / "healthcheck.sh")],
        cwd=ROOT,
        env={"PATH": str(tmp_path) + os.pathsep + os.defpath},
        text=True,
        capture_output=True,
        check=False,
    )


def test_healthcheck_uses_dotenv_port_and_script_directory(tmp_path):
    result = run_healthcheck(tmp_path, "UVICORN_PORT=9123\n")
    assert result.returncode == 0, result.stderr
    assert "http://127.0.0.1:9123/health" in result.stdout


def test_healthcheck_rejects_invalid_tls_in_dotenv(tmp_path):
    result = run_healthcheck(tmp_path, "UVICORN_SSL_CERTFILE=/cert.pem\n")
    assert result.returncode != 0
    assert "configured together" in result.stderr
    assert "/health" not in result.stdout
