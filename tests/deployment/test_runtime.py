"""Dependency-free deployment regressions: python -m unittest discover -s tests/deployment -v."""

import asyncio
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_lifecycle():
    spec = importlib.util.spec_from_file_location("isolated_lifecycle", ROOT / "app/lifecycle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_phases_override_late_registration_but_preserve_phase_order(self):
        lifecycle = load_lifecycle()
        calls = []
        lifecycle.on_shutdown(lambda: calls.append("close"), phase=lifecycle.ShutdownPhase.TRANSPORTS)
        lifecycle.on_shutdown(lambda: calls.append("flush"), phase=lifecycle.ShutdownPhase.DRAIN)
        lifecycle.on_shutdown(lambda: calls.append("stop-node"), phase=lifecycle.ShutdownPhase.PRODUCERS)
        lifecycle.on_startup(
            lambda: lifecycle.on_shutdown(lambda: calls.append("stop-loops"), phase=lifecycle.ShutdownPhase.QUIESCE)
        )
        async with lifecycle.lifespan(None):
            pass
        self.assertEqual(calls, ["stop-loops", "stop-node", "flush", "close"])

    async def test_timed_out_hook_does_not_skip_transport_cleanup(self):
        lifecycle = load_lifecycle()
        lifecycle.configure_shutdown(timeout=0.2, hook_timeout=0.03)
        calls = []

        async def hanging():
            await asyncio.Event().wait()

        lifecycle.on_shutdown(hanging, phase=lifecycle.ShutdownPhase.DRAIN)
        lifecycle.on_shutdown(lambda: calls.append("close"), phase=lifecycle.ShutdownPhase.TRANSPORTS)
        started = asyncio.get_running_loop().time()
        with self.assertLogs("isolated_lifecycle", level="ERROR"), self.assertRaises(ExceptionGroup):
            async with lifecycle.lifespan(None):
                pass
        self.assertEqual(calls, ["close"])
        self.assertLess(asyncio.get_running_loop().time() - started, 0.5)

    async def test_cancel_suppressing_hook_cannot_hold_lifespan_forever(self):
        lifecycle = load_lifecycle()
        lifecycle.configure_shutdown(timeout=0.1, hook_timeout=0.02)
        finish = asyncio.Event()
        cancelled = asyncio.Event()

        async def stubborn():
            try:
                await finish.wait()
            except asyncio.CancelledError:
                cancelled.set()
                await finish.wait()

        lifecycle.on_shutdown(stubborn)
        try:
            with self.assertLogs("isolated_lifecycle", level="ERROR"), self.assertRaises(ExceptionGroup):
                async with lifecycle.lifespan(None):
                    pass
            await asyncio.wait_for(cancelled.wait(), 0.1)
            with self.assertRaisesRegex(RuntimeError, "Previous cleanup"):
                async with lifecycle.lifespan(None):
                    pass
        finally:
            finish.set()
            if lifecycle._lingering_cleanup:
                await asyncio.gather(*lifecycle._lingering_cleanup)

    async def test_duplicate_registration_does_not_erase_explicit_phase(self):
        lifecycle = load_lifecycle()
        callback = lambda: None
        lifecycle.on_shutdown(callback, phase=lifecycle.ShutdownPhase.TRANSPORTS)
        lifecycle.on_shutdown(callback)
        self.assertEqual(lifecycle._shutdown_phases[callback], lifecycle.ShutdownPhase.TRANSPORTS)
        self.assertEqual(lifecycle.shutdown_functions.count(callback), 1)

    async def test_cleanup_after_body_error(self):
        lifecycle = load_lifecycle()
        calls = []
        lifecycle.on_shutdown(lambda: calls.append("closed"))
        with self.assertRaisesRegex(ValueError, "body"):
            async with lifecycle.lifespan(None):
                raise ValueError("body")
        self.assertEqual(calls, ["closed"])

    async def test_cleanup_after_partial_startup(self):
        lifecycle = load_lifecycle()
        calls = []

        def fail():
            raise ValueError("startup")

        lifecycle.on_startup(fail)
        lifecycle.on_shutdown(lambda: calls.append("closed"))
        with self.assertRaisesRegex(ValueError, "startup"):
            async with lifecycle.lifespan(None):
                self.fail("startup must fail")
        self.assertEqual(calls, ["closed"])

    async def test_failed_cleanup_does_not_skip_remaining_hooks(self):
        lifecycle = load_lifecycle()
        calls = []

        def fail():
            raise RuntimeError("cleanup")

        lifecycle.on_shutdown(fail)
        lifecycle.on_shutdown(lambda: calls.append("closed"))
        with self.assertLogs("isolated_lifecycle", level="ERROR"), self.assertRaises(ExceptionGroup):
            async with lifecycle.lifespan(None):
                pass
        self.assertEqual(calls, ["closed"])

    async def test_cleanup_error_preserves_original_error(self):
        lifecycle = load_lifecycle()

        def fail():
            raise RuntimeError("cleanup")

        lifecycle.on_shutdown(fail)
        with self.assertLogs("isolated_lifecycle", level="ERROR"), self.assertRaisesRegex(ValueError, "original"):
            async with lifecycle.lifespan(None):
                raise ValueError("original")

    async def test_sync_callable_returning_awaitable(self):
        lifecycle = load_lifecycle()
        calls = []

        async def callback(app):
            await asyncio.sleep(0)
            calls.append(app)

        lifecycle.on_startup(lambda app: callback(app))
        async with lifecycle.lifespan("app"):
            self.assertEqual(calls, ["app"])

    async def test_cancelled_cleanup_does_not_skip_other_hooks(self):
        lifecycle = load_lifecycle()
        calls = []

        async def cancelled():
            raise asyncio.CancelledError("cleanup cancelled")

        lifecycle.on_shutdown(cancelled)
        lifecycle.on_shutdown(lambda: calls.append("closed"))
        with self.assertLogs("isolated_lifecycle", level="ERROR"), self.assertRaises(BaseExceptionGroup):
            async with lifecycle.lifespan(None):
                pass
        self.assertEqual(calls, ["closed"])

    async def test_body_cancellation_is_preserved_after_failed_cleanup(self):
        lifecycle = load_lifecycle()

        def fail():
            raise RuntimeError("cleanup")

        lifecycle.on_shutdown(fail)
        with self.assertLogs("isolated_lifecycle", level="ERROR"), self.assertRaises(asyncio.CancelledError):
            async with lifecycle.lifespan(None):
                raise asyncio.CancelledError("body cancelled")

    async def test_overlapping_lifespans_are_rejected_without_cleaning_up_owner(self):
        lifecycle = load_lifecycle()
        calls = []
        lifecycle.on_shutdown(lambda: calls.append("closed"))
        async with lifecycle.lifespan("owner"):
            with self.assertRaisesRegex(RuntimeError, "one application lifespan"):
                async with lifecycle.lifespan("other"):
                    self.fail("second lifespan must not start")
            self.assertEqual(calls, [])
        self.assertEqual(calls, ["closed"])

    async def test_failed_startup_releases_lifespan_guard(self):
        lifecycle = load_lifecycle()

        def fail():
            raise ValueError("startup")

        lifecycle.on_startup(fail)
        with self.assertRaises(ValueError):
            async with lifecycle.lifespan(None):
                pass
        lifecycle.startup_functions.clear()
        async with lifecycle.lifespan(None):
            pass


class HealthcheckTests(unittest.TestCase):
    def check_port(self, explicit, platform, expected):
        with tempfile.TemporaryDirectory() as directory:
            curl = Path(directory) / "curl"
            curl.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            curl.chmod(0o755)
            env = {"PATH": directory + os.pathsep + os.defpath}
            if explicit:
                env["UVICORN_PORT"] = explicit
            if platform:
                env["PORT"] = platform
            result = subprocess.run(
                ["bash", str(ROOT / "healthcheck.sh")], env=env, text=True, capture_output=True, check=True
            )
            self.assertIn(f"http://127.0.0.1:{expected}/health", result.stdout)
            self.assertIn("--max-time\n5", result.stdout)

    def check_worker_role(self, role):
        with tempfile.TemporaryDirectory() as directory:
            python = Path(directory) / "python"
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            python.chmod(0o755)
            result = subprocess.run(
                ["bash", str(ROOT / "healthcheck.sh")],
                env={"PATH": directory + os.pathsep + os.defpath, "ROLE": role},
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("/proc/1/cmdline", result.stdout)
            self.assertTrue(result.stdout.rstrip().endswith(role))

    def test_node_worker_does_not_probe_http(self):
        self.check_worker_role("node")

    def test_scheduler_worker_does_not_probe_http(self):
        self.check_worker_role("scheduler")

    def test_platform_port(self):
        self.check_port(None, "9000", "9000")

    def test_explicit_port_takes_precedence(self):
        self.check_port("8080", "9000", "8080")

    def test_default_port(self):
        self.check_port(None, None, "8000")


if __name__ == "__main__":
    unittest.main()
