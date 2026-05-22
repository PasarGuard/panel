import math
import os
import secrets
import time
from dataclasses import dataclass

import psutil


@dataclass
class MemoryStat:
    total: int
    used: int
    free: int


@dataclass
class CPUStat:
    cores: int
    percent: float


@dataclass
class DiskStat:
    total: int
    used: int
    free: int


def cpu_usage() -> CPUStat:
    return CPUStat(cores=psutil.cpu_count(), percent=psutil.cpu_percent())


def memory_usage() -> MemoryStat:
    mem = psutil.virtual_memory()
    # Estimate active memory by excluding file cache when available.
    if hasattr(mem, "free") and hasattr(mem, "cached"):
        used = mem.total - mem.free - mem.cached
        # Guard against unexpected platform-specific values.
        if used < 0 or used > mem.total:
            used = mem.used
    else:
        used = mem.used

    return MemoryStat(total=mem.total, used=used, free=mem.available)


def disk_usage(path: str | None = None) -> DiskStat:
    usage_path = path or os.path.abspath(os.sep)
    try:
        disk = psutil.disk_usage(usage_path)
    except Exception:
        # Fallback to the current working directory if root path is unavailable.
        disk = psutil.disk_usage(".")

    return DiskStat(total=disk.total, used=disk.used, free=disk.free)


def get_uptime() -> int:
    pid = os.getpid()
    process = psutil.Process(pid)
    create_time = process.create_time()
    return int(time.time() - create_time)


def random_password() -> str:
    return secrets.token_urlsafe(24)


def readable_size(size_bytes):
    if not size_bytes or size_bytes <= 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


def readable_duration(seconds: int | float) -> str:
    """Format a duration (in seconds) as a human-readable string.

    Mirrors :func:`readable_size`: caller always passes seconds, this picks the
    largest natural unit (years, months, days, hours, minutes, seconds) and
    pluralizes correctly.
    """
    if not seconds or seconds <= 0:
        return "0 seconds"

    units = (
        ("year", 31_536_000),  # 365 days
        ("month", 2_592_000),  # 30 days
        ("day", 86_400),
        ("hour", 3_600),
        ("minute", 60),
        ("second", 1),
    )

    for label, factor in units:
        if seconds >= factor:
            amount = seconds / factor
            if amount % 1 == 0:
                amount_int = int(amount)
                return f"{amount_int} {label}" if amount_int == 1 else f"{amount_int} {label}s"
            return f"{amount:.2f} {label}s"

    return f"{seconds} seconds"
