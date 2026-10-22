"""Run factory checks in a fresh interpreter to isolate process-global services."""

import os
import subprocess
import sys


def test_repeated_factory_does_not_accumulate_lifecycle_or_leader_callbacks():
    code = """
from app import create_app
from app.lifecycle import startup_functions, shutdown_functions
from app.nats import leader
first = create_app()
from app.notification.client import close_notification_client
from app.jobs.send_notifications import send_pending_notifications_before_shutdown
dispatcher_stop = next(hook for hook in shutdown_functions if hook.__name__ == "_stop_notification_dispatcher_if_started")
assert shutdown_functions.index(dispatcher_stop) < shutdown_functions.index(close_notification_client)
assert shutdown_functions.index(send_pending_notifications_before_shutdown) < shutdown_functions.index(close_notification_client)
counts = (len(startup_functions), len(shutdown_functions), len(leader._on_leadership_lost or []))
for _ in range(100):
    other = create_app()
    assert other is not first
    assert (len(startup_functions), len(shutdown_functions), len(leader._on_leadership_lost or [])) == counts
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "ROLE": "all-in-one", "NATS_ENABLED": "false", "UVICORN_WORKERS": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_all_roles_register_cleanup_for_both_notification_queues():
    code = """
from app import create_app
from app.lifecycle import shutdown_functions
from app.notification.client import close_notification_client
from app.notification.queue_manager import shutdown_queues, shutdown_webhook_queue
create_app()
for hook in (close_notification_client, shutdown_queues, shutdown_webhook_queue):
    assert shutdown_functions.count(hook) == 1, hook.__name__
"""
    for role in ("backend", "node", "scheduler", "all-in-one"):
        result = subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "ROLE": role, "NATS_ENABLED": "true", "UVICORN_WORKERS": "1"},
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert result.returncode == 0, f"{role}: {result.stderr}"
