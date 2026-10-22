"""Railway profile checks: stdlib only; never import or touch an application DB."""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from railway_runtime import (
    CREDENTIALS_FILE,
    RailwayConfigurationError,
    acquire_instance_lock,
    automatic_profile_enabled,
    configure_environment,
    initial_credentials,
    read_credentials,
)


class RailwayProfileTests(unittest.TestCase):
    def test_detection_and_explicit_opt_out(self):
        self.assertFalse(automatic_profile_enabled({}))
        self.assertTrue(automatic_profile_enabled({"RAILWAY_ENVIRONMENT_ID": "test"}))
        self.assertFalse(
            automatic_profile_enabled({"RAILWAY_ENVIRONMENT_ID": "test", "PASARGUARD_RAILWAY_AUTO_CONFIG": "false"})
        )
        with self.assertRaises(RailwayConfigurationError):
            automatic_profile_enabled({"RAILWAY_ENVIRONMENT_ID": "test", "PASARGUARD_RAILWAY_AUTO_CONFIG": "typo"})

    def test_no_ephemeral_fallback(self):
        for env, mounted in [({}, False), ({"RAILWAY_VOLUME_MOUNT_PATH": "/elsewhere"}, True)]:
            with self.subTest(env=env), self.assertRaises(RailwayConfigurationError):
                configure_environment(env, mounted=mounted)

    def test_defaults_and_no_mutation(self):
        env = {"PORT": "9010", "RAILWAY_PUBLIC_DOMAIN": "panel.up.railway.app"}
        result = configure_environment(env, mounted=True)
        self.assertEqual(result["PORT"], "9010")
        self.assertEqual(result["ALLOWED_ORIGINS"], "https://panel.up.railway.app")
        self.assertEqual(result["SQLALCHEMY_DATABASE_URL"], "sqlite+aiosqlite:////data/db.sqlite3")
        self.assertEqual(result["UVICORN_WORKERS"], "1")
        self.assertEqual(result["PASARGUARD_RAILWAY_READY"], "1")
        self.assertNotIn("DEBUG", env)

    def test_no_domain_means_same_origin_only(self):
        result = configure_environment({}, mounted=True)
        self.assertEqual(result["ALLOWED_ORIGINS"], "")
        self.assertEqual(result["PORT"], "8080")

    def test_rejects_unsafe_overrides(self):
        cases = [
            {"DEBUG": "true"},
            {"TESTING": "true"},
            {"ROLE": "node"},
            {"UVICORN_HOST": "127.0.0.1"},
            {"UVICORN_WORKERS": "2"},
            {"NATS_ENABLED": "true"},
            {"UVICORN_ALLOW_INSECURE_HTTP": "false"},
            {"SQLALCHEMY_DATABASE_URL": "sqlite+aiosqlite:////tmp/db.sqlite3"},
            {"SQLALCHEMY_DATABASE_URL": "sqlite+aiosqlite:////data/DB.sqlite3"},
            {"PORT": "8080", "UVICORN_PORT": "8000"},
            {"UVICORN_UDS": "/tmp/socket"},
            {"UVICORN_SSL_CERTFILE": "cert.pem"},
            {"ALLOWED_ORIGINS": "*"},
            {"RAILWAY_PUBLIC_DOMAIN": "https://example.com/path"},
        ]
        for env in cases:
            with self.subTest(env=env), self.assertRaises(RailwayConfigurationError):
                configure_environment(env, mounted=True)

    def test_invalid_ports(self):
        for value in ["", "0", "65536", "-1", "abc", "８０８０"]:
            with self.subTest(value=value), self.assertRaises(RailwayConfigurationError):
                configure_environment({"PORT": value}, mounted=True)

    def test_strong_stable_private_credentials(self):
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent) / "private"
            first = initial_credentials(directory)
            self.assertEqual(first, initial_credentials(directory))
            self.assertEqual(first["username"], "owner")
            self.assertTrue(first["password"].startswith("AaBb12!"))
            self.assertGreaterEqual(len(first["password"]), 40)
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((directory / CREDENTIALS_FILE).stat().st_mode), 0o600)
            self.assertEqual(list(directory.iterdir()), [directory / CREDENTIALS_FILE])

    def test_refuses_exposed_or_corrupt_credentials(self):
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent)
            record = initial_credentials(directory)
            path = directory / CREDENTIALS_FILE
            path.chmod(0o644)
            with self.assertRaises(RailwayConfigurationError):
                read_credentials(directory)
            path.chmod(0o600)
            path.write_text("{incomplete")
            with self.assertRaises(json.JSONDecodeError):
                initial_credentials(directory)
            self.assertNotIn(record["password"], path.read_text())

    def test_refuses_symlink_file_and_directory(self):
        with tempfile.TemporaryDirectory() as parent:
            parent = Path(parent)
            directory = parent / "private"
            directory.mkdir(mode=0o700)
            target = parent / "target"
            target.write_text("do not overwrite")
            (directory / CREDENTIALS_FILE).symlink_to(target)
            with self.assertRaises(OSError):
                initial_credentials(directory)
            self.assertEqual(target.read_text(), "do not overwrite")
            link = parent / "link"
            link.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(RailwayConfigurationError):
                initial_credentials(link)

    def test_refuses_public_directory(self):
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent)
            directory.chmod(0o755)
            with self.assertRaises(RailwayConfigurationError):
                initial_credentials(directory)

    def test_failed_publication_leaves_no_partial_final_file(self):
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent)
            with patch("railway_runtime.os.link", side_effect=OSError("disk failure")), self.assertRaises(OSError):
                initial_credentials(directory)
            self.assertEqual(list(directory.iterdir()), [])
            initial_credentials(directory)  # A retry can still succeed.

    def test_lock_is_inheritable_exclusive_and_released(self):
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent)
            fd = acquire_instance_lock(directory)
            try:
                self.assertTrue(os.get_inheritable(fd))
                script = "from pathlib import Path; from railway_runtime import acquire_instance_lock; acquire_instance_lock(Path(__import__('sys').argv[1]))"
                result = subprocess.run(
                    [sys.executable, "-c", script, str(directory)],
                    cwd=ROOT,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"BlockingIOError", result.stderr)
            finally:
                os.close(fd)
            fd = acquire_instance_lock(directory)
            os.close(fd)


if __name__ == "__main__":
    unittest.main()
