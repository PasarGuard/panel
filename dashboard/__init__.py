import atexit
import os
import re
import subprocess
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app import on_startup
from config import dashboard_settings, runtime_settings, server_settings

base_dir = Path(__file__).parent
build_dir = base_dir / "build"
statics_dir = build_dir / "statics"
NO_CACHE_FILENAMES = {"index.html", "404.html", "sw.js", "manifest.webmanifest"}
HASHED_ASSET_RE = re.compile(r".+-[A-Za-z0-9_-]{6,}\.[A-Za-z0-9]+$")


class DashboardStaticFiles(StaticFiles):
    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        file_name = Path(full_path).name

        if file_name in NO_CACHE_FILENAMES:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        elif HASHED_ASSET_RE.match(file_name):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers.setdefault("Cache-Control", "public, max-age=3600")

        return response


def build_api_interface():
    subprocess.Popen(
        ["bun", "run", "wait-port-gen-api"],
        env={**os.environ, "UVICORN_PORT": str(server_settings.port)},
        cwd=base_dir,
        stdout=subprocess.DEVNULL,
    )


def build():
    proc = subprocess.Popen(
        ["bun", "run", "build", "--outDir", build_dir, "--assetsDir", "statics"],
        env={**os.environ, "VITE_BASE_API": dashboard_settings.vite_base_api},
        cwd=base_dir,
    )
    proc.wait()
    with open(build_dir / "index.html", "r") as file:
        html = file.read()
    with open(build_dir / "404.html", "w") as file:
        file.write(html)


def run_dev():
    build_api_interface()
    proc = subprocess.Popen(
        ["bun", "run", "dev", "--base", os.path.join(dashboard_settings.path, "")],
        env={**os.environ, "VITE_BASE_API": dashboard_settings.vite_base_api, "DEBUG": "false"},
        cwd=base_dir,
    )

    atexit.register(proc.terminate)


def run_build(app):
    if runtime_settings.role.runs_panel and not build_dir.is_dir():
        build()

    app.mount(dashboard_settings.path, DashboardStaticFiles(directory=build_dir, html=True), name="dashboard")
    app.mount("/statics/", DashboardStaticFiles(directory=statics_dir, html=True), name="statics")


def setup_dashboard(app):
    @on_startup
    def run_dashboard():
        if runtime_settings.debug:
            run_dev()
        else:
            run_build(app)
