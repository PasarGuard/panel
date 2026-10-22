"""Run the entrypoint against a fake interpreter; never touch an application DB."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class EntrypointTests(unittest.TestCase):
    def run_entrypoint(self, role, migration_status=0, *, railway_ready=False, bootstrap_status=0):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            trace = directory / "trace"
            python = directory / "python"
            python.write_text("""#!/bin/sh
printf '%s|%s|%s\\n' "$PWD" "$ROLE" "$*" >> "$TRACE"
if [ "$2" = "cli.railway" ]; then exit "$BOOTSTRAP_STATUS"; fi
if [ "$1" = "-m" ]; then exit "$MIGRATION_STATUS"; fi
""")
            python.chmod(0o755)
            result = subprocess.run(
                ["bash", str(ROOT / "start.sh")],
                cwd=directory,
                check=False,
                capture_output=True,
                text=True,
                env={
                    "PATH": str(directory) + os.pathsep + os.defpath,
                    "ROLE": role,
                    "TRACE": str(trace),
                    "MIGRATION_STATUS": str(migration_status),
                    "PASARGUARD_RAILWAY_READY": "1" if railway_ready else "",
                    "BOOTSTRAP_STATUS": str(bootstrap_status),
                },
            )
            return result, trace.read_text().splitlines() if trace.exists() else []

    def test_migration_failure_prevents_server_and_preserves_exit_status(self):
        result, trace = self.run_entrypoint("all-in-one", migration_status=17)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(len(trace), 1)
        self.assertIn("-m alembic upgrade head", trace[0])

    def test_invalid_role_never_runs_migration(self):
        result, trace = self.run_entrypoint("mistyped")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(trace, [])

    def test_worker_role_is_normalized_and_runs_from_repository(self):
        result, trace = self.run_entrypoint("  NODE  ")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(trace, [f"{ROOT}|node|node_worker.py"])

    def test_panel_runs_migration_before_server(self):
        result, trace = self.run_entrypoint("backend")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(trace, [f"{ROOT}|backend|-m alembic upgrade head", f"{ROOT}|backend|main.py"])

    def test_dotenv_role_uses_parser_not_shell_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            entrypoint = directory / "start.sh"
            entrypoint.write_text((ROOT / "start.sh").read_text())
            (directory / ".env").write_text("ROLE=scheduler\nBAD=$(touch unexpected)\n")
            python = directory / "python"
            python.write_text("""#!/bin/sh
if [ "$1" = "-c" ]; then printf 'scheduler\\n'; else printf '%s' "$*"; fi
""")
            python.chmod(0o755)
            result = subprocess.run(
                ["bash", str(entrypoint)],
                cwd=directory,
                text=True,
                capture_output=True,
                check=True,
                env={"PATH": str(directory) + os.pathsep + os.defpath},
            )
            self.assertEqual(result.stdout, "scheduler_worker.py")
            self.assertFalse((directory / "unexpected").exists())


class RailwayEntrypointTests(unittest.TestCase):
    run_entrypoint = EntrypointTests.run_entrypoint

    def test_migration_then_bootstrap_then_server(self):
        result, trace = self.run_entrypoint("all-in-one", railway_ready=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            [line.split("|")[-1] for line in trace], ["-m alembic upgrade head", "-m cli.railway", "main.py"]
        )

    def test_bootstrap_failure_prevents_server(self):
        result, trace = self.run_entrypoint("all-in-one", railway_ready=True, bootstrap_status=19)
        self.assertEqual(result.returncode, 19)
        self.assertEqual(len(trace), 2)

    def test_migration_failure_prevents_bootstrap(self):
        result, trace = self.run_entrypoint("all-in-one", railway_ready=True, migration_status=17)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(len(trace), 1)
