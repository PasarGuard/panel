"""Fail-closed, single-instance Railway profile. No cloud API or secret logging.

Only the entrypoint enables this profile. Importing this module has no effects.
Railway resources (volume/domain/plan) must still be provisioned by the account owner.
"""

import json
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path

DATA_DIR = Path("/data")
PRIVATE_DIR = DATA_DIR / ".pasarguard"
CREDENTIALS_FILE = "initial-owner.json"


class RailwayConfigurationError(RuntimeError):
    pass


def automatic_profile_enabled(env: dict[str, str]) -> bool:
    if not env.get("RAILWAY_ENVIRONMENT_ID"):
        return False
    value = env.get("PASARGUARD_RAILWAY_AUTO_CONFIG", "true").strip().lower()
    if value not in {"true", "false"}:
        raise RailwayConfigurationError("PASARGUARD_RAILWAY_AUTO_CONFIG must be true or false")
    return bool(env.get("RAILWAY_ENVIRONMENT_ID")) and value == "true"


def volume_is_mounted() -> bool:
    # mountinfo also detects same-filesystem bind mounts that ismount can miss.
    try:
        with open("/proc/self/mountinfo") as mounts:
            return any(len(fields := line.split()) > 4 and fields[4] == str(DATA_DIR) for line in mounts)
    except OSError:
        return os.path.ismount(DATA_DIR)


def configure_environment(env: dict[str, str], *, mounted: bool) -> dict[str, str]:
    """Return a copy; reject unsafe overrides instead of silently ignoring them."""
    if not mounted or env.get("RAILWAY_VOLUME_MOUNT_PATH", "/data") != "/data":
        raise RailwayConfigurationError(
            "Attach a persistent Railway volume at /data, then redeploy. No ephemeral fallback."
        )
    result = dict(env)
    required = {
        "ROLE": "all-in-one",
        "DEBUG": "false",
        "TESTING": "false",
        "ECHO_SQL_QUERIES": "false",
        "UVICORN_HOST": "0.0.0.0",
        "UVICORN_ALLOW_INSECURE_HTTP": "true",
        "UVICORN_WORKERS": "1",
        "NATS_ENABLED": "false",
        "SQLALCHEMY_DATABASE_URL": "sqlite+aiosqlite:////data/db.sqlite3",
    }
    for key, expected in required.items():
        actual = result.get(key, expected).strip()
        if key in {"ROLE", "DEBUG", "TESTING", "ECHO_SQL_QUERIES", "NATS_ENABLED", "UVICORN_ALLOW_INSECURE_HTTP"}:
            actual = actual.lower()
        if actual != expected:
            raise RailwayConfigurationError(f"{key} conflicts with the automatic SQLite profile; remove the override.")
        result[key] = expected
    if result.get("UVICORN_UDS") or result.get("UVICORN_SSL_CERTFILE") or result.get("UVICORN_SSL_KEYFILE"):
        raise RailwayConfigurationError("Remove UDS/local TLS settings; this profile uses Railway HTTPS termination.")
    port = result.get("UVICORN_PORT", result.get("PORT", "8080"))
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise RailwayConfigurationError("PORT/UVICORN_PORT must be an integer between 1 and 65535.")
    if result.get("UVICORN_PORT") and result.get("PORT") and result["UVICORN_PORT"] != result["PORT"]:
        raise RailwayConfigurationError("UVICORN_PORT conflicts with Railway PORT; remove UVICORN_PORT.")
    result["PORT"] = port
    domain = result.get("RAILWAY_PUBLIC_DOMAIN", "")
    if domain and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", domain):
        raise RailwayConfigurationError("RAILWAY_PUBLIC_DOMAIN must be a hostname, not a URL.")
    # An empty CORS list still permits same-origin requests; never default to '*'.
    result.setdefault("ALLOWED_ORIGINS", f"https://{domain}" if domain else "")
    if "*" in result["ALLOWED_ORIGINS"]:
        raise RailwayConfigurationError("Wildcard ALLOWED_ORIGINS is not permitted in the automatic profile.")
    result["PASARGUARD_RAILWAY_READY"] = "1"
    return result


def ensure_private_directory(directory: Path) -> None:
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise RailwayConfigurationError("Bootstrap directory must be a non-symlink owned by this user, with mode 0700.")


def read_credentials(directory: Path) -> dict[str, str]:
    path = directory / CREDENTIALS_FILE
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise RailwayConfigurationError("Initial credentials must be a private, regular file with mode 0600.")
        if info.st_size > 4096:
            raise RailwayConfigurationError("Invalid initial credentials file.")
        record = json.load(stream)
    if (
        not isinstance(record, dict)
        or record.get("username") != "owner"
        or not isinstance(record.get("password"), str)
        or not 12 <= len(record["password"]) <= 72
    ):
        raise RailwayConfigurationError("Invalid initial credentials file; refusing to overwrite it.")
    return record


def initial_credentials(directory: Path) -> dict[str, str]:
    """Publish fully written secrets atomically, before committing the DB owner.

    A crash after publication can retry with the same password. Never replace an
    existing credential file, including dangling symlinks. No secrets reach logs.
    """
    ensure_private_directory(directory)
    if os.path.lexists(directory / CREDENTIALS_FILE):
        return read_credentials(directory)
    record = {"username": "owner", "password": "AaBb12!" + secrets.token_urlsafe(32)}
    fd, temporary = tempfile.mkstemp(prefix=".owner-", dir=directory)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(record, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, directory / CREDENTIALS_FILE)
        except FileExistsError:
            return read_credentials(directory)
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.unlink(temporary)
    return record


def acquire_instance_lock(directory: Path) -> int:
    """The inheritable FD holds the lock through bash's final exec of Python."""
    import fcntl

    ensure_private_directory(directory)
    fd = os.open(directory / "runtime.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RailwayConfigurationError("Runtime lock must be a regular file.")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.set_inheritable(fd, True)
    except BaseException:
        os.close(fd)
        raise
    return fd


def main() -> None:
    try:
        if not automatic_profile_enabled(dict(os.environ)):
            raise RailwayConfigurationError("This entrypoint requires Railway automatic configuration to be enabled.")
        env = configure_environment(dict(os.environ), mounted=volume_is_mounted())
        acquire_instance_lock(PRIVATE_DIR)
        os.execve("/bin/bash", ["bash", str(Path(__file__).resolve().parent / "start.sh")], env)
    except RailwayConfigurationError as exc:
        raise SystemExit(f"Railway configuration: {exc}") from None
    except BlockingIOError:
        raise SystemExit(
            "Another panel instance holds the volume lock. Use one replica; stop the old instance first."
        ) from None
    except Exception as exc:
        raise SystemExit(f"Railway initialization failed ({type(exc).__name__}); no secret values logged.") from None


if __name__ == "__main__":
    main()
