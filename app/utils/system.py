import ipaddress
import math
import os
import secrets
import socket
import time
import urllib.request
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


def check_port(port: int) -> bool:
    s = socket.socket()
    try:
        s.connect(("127.0.0.1", port))
        return True
    except socket.error:
        return False
    finally:
        s.close()


def _fetch_text(url: str, timeout: float = 5.0) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                return None
            return response.read().decode("utf-8").strip()
    except Exception:
        return None


def _get_public_ipv4() -> str | None:
    urls = (
        "https://api.ipify.org/",
        "https://ipv4.icanhazip.com/",
        "https://ifconfig.io/ip",
    )
    for url in urls:
        ip = _fetch_text(url)
        if not ip:
            continue
        try:
            if ipaddress.IPv4Address(ip).is_global:
                return ip
        except Exception:
            continue

    return None


def get_public_ip():
    ip = _get_public_ipv4()
    if ip:
        return ip

    return "127.0.0.1"


def _get_public_ipv6() -> str | None:
    urls = (
        "https://api6.ipify.org/",
        "https://ipv6.icanhazip.com/",
    )
    for url in urls:
        ip = _fetch_text(url)
        if not ip:
            continue
        try:
            if ipaddress.IPv6Address(ip).is_global:
                return "[%s]" % ip
        except Exception:
            continue

    return None


def get_public_ipv6():
    ip = _get_public_ipv6()
    if ip:
        return ip

    return "[::1]"


def readable_size(size_bytes):
    if not size_bytes or size_bytes <= 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"
