import atexit
import os
import signal
import subprocess
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app import app, on_shutdown, on_startup
from config import DASHBOARD_PATH, DEBUG, UVICORN_PORT, VITE_BASE_API

base_dir = Path(__file__).parent
build_dir = base_dir / "build"
statics_dir = build_dir / "statics"
_dev_proc: subprocess.Popen | None = None
_api_proc: subprocess.Popen | None = None


def _terminate_process(proc: subprocess.Popen | None) -> None:
    if not proc or proc.poll() is not None:
        return

    try:
        if os.name == "nt":
            proc.terminate()
            proc.wait(timeout=1)
            if proc.poll() is None:
                proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        return


def stop_dashboard_processes() -> None:
    global _dev_proc, _api_proc
    _terminate_process(_api_proc)
    _terminate_process(_dev_proc)
    _api_proc = None
    _dev_proc = None


def build_api_interface():
    global _api_proc
    if _api_proc and _api_proc.poll() is None:
        return
    _api_proc = subprocess.Popen(
        ["bun", "run", "wait-port-gen-api"],
        env={**os.environ, "UVICORN_PORT": str(UVICORN_PORT)},
        cwd=base_dir,
        stdout=subprocess.DEVNULL,
        start_new_session=True,
    )


def build():
    proc = subprocess.Popen(
        ["bun", "run", "build", "--outDir", build_dir, "--assetsDir", "statics"],
        env={**os.environ, "VITE_BASE_API": VITE_BASE_API},
        cwd=base_dir,
    )
    proc.wait()
    with open(build_dir / "index.html", "r") as file:
        html = file.read()
    with open(build_dir / "404.html", "w") as file:
        file.write(html)


def run_dev():
    global _dev_proc
    if _dev_proc and _dev_proc.poll() is None:
        return
    build_api_interface()
    _dev_proc = subprocess.Popen(
        ["bun", "run", "dev", "--base", os.path.join(DASHBOARD_PATH, "")],
        env={**os.environ, "VITE_BASE_API": VITE_BASE_API, "DEBUG": "false"},
        cwd=base_dir,
        start_new_session=True,
    )


def run_build():
    if not build_dir.is_dir():
        build()

    app.mount(DASHBOARD_PATH, StaticFiles(directory=build_dir, html=True), name="dashboard")
    app.mount("/statics/", StaticFiles(directory=statics_dir, html=True), name="statics")


@on_startup
def run_dashboard():
    if DEBUG:
        if os.getenv("DASHBOARD_DEV_MANAGED", "").lower() in {"1", "true", "yes"}:
            return
        run_dev()
    else:
        run_build()


@on_shutdown
def shutdown_dashboard():
    stop_dashboard_processes()


atexit.register(stop_dashboard_processes)
