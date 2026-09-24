"""Export the OpenAPI schema (and optionally regenerate the API client) offline.

FastAPI builds its schema purely from the route table, so we can construct the
app in-process and call ``app.openapi()`` instead of booting uvicorn + DB + NATS.

The ALL_IN_ONE role is the only one that mounts the panel/API routes while not
requiring NATS, so we force it here (env var wins over any .env value). Nothing
in ``create_app()`` touches the DB/NATS at construction time — those are all
registered as on_startup hooks that never fire in this script.

Usage:
    uv run python scripts/export_openapi.py [output_path]
    uv run python scripts/export_openapi.py --gen-client   # also run orval

Why Python drives orval instead of the Makefile: setting an env var inline
(``VAR=val cmd``) is POSIX-shell syntax and fails under Windows cmd.exe, which
is the default shell GNU make uses on Windows. Setting it via ``os.environ`` and
spawning orval through subprocess is portable across Windows/macOS/Linux.

NOTE: the app is imported lazily inside ``export_schema`` via importlib on
purpose. A top-level ``from app...`` import gets hoisted by import sorters
(ruff/isort, editor "organize imports") above the ROLE/sys.path setup below,
which breaks both the import path and the role override. Keep it lazy.
"""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

# Force a role that mounts the API routes without requiring NATS. Must happen
# before app/config import (which reads ROLE). Env var wins over .env.
os.environ["ROLE"] = "all-in-one"

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = REPO_ROOT / "dashboard"

# Ensure the repo root is importable whether run as `python scripts/x.py`
# (script dir on path) or `python -m scripts.x` (cwd on path).
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def export_schema(output: Path) -> None:
    create_app = importlib.import_module("app.app_factory").create_app

    app = create_app()
    schema = app.openapi()
    if not schema or not schema.get("paths"):
        raise SystemExit("OpenAPI schema is empty — no routes were registered.")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OpenAPI schema written to {output} ({len(schema['paths'])} paths)")


def run_orval(schema_path: Path) -> None:
    # orval reads input.target from process.env.OPENAPI_INPUT (see orval.config.ts).
    env = {**os.environ, "OPENAPI_INPUT": str(schema_path.resolve())}
    cmd = ["bun", "run", "gen:api"]
    print(f"Running orval: {' '.join(cmd)} (cwd={DASHBOARD_DIR})")
    try:
        proc = subprocess.run(cmd, cwd=DASHBOARD_DIR, env=env, check=False)
    except FileNotFoundError:
        raise SystemExit("`bun` was not found on PATH. Install bun or run `make install-front` first.")
    if proc.returncode != 0:
        raise SystemExit(f"orval failed with exit code {proc.returncode}")


def main() -> None:
    args = sys.argv[1:]
    gen_client = "--gen-client" in args
    positional = [a for a in args if not a.startswith("-")]

    output = Path(positional[0]) if positional else DASHBOARD_DIR / "openapi.json"
    export_schema(output)

    if gen_client:
        run_orval(output)


if __name__ == "__main__":
    main()
