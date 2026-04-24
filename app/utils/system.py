import asyncio
import ipaddress
import math
import os
import secrets
import socket
from dataclasses import dataclass

import aiohttp
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


async def _fetch_text(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(url) as response:
            if response.status != 200:
                return None
            return (await response.text()).strip()
    except Exception:
        return None


async def _get_public_ipv4_async() -> str | None:
    urls = (
        "http://api4.ipify.org/",
        "http://ipv4.icanhazip.com/",
        "https://ifconfig.io/ip",
    )
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [asyncio.ensure_future(_fetch_text(session, url)) for url in urls]
        try:
            for finished in asyncio.as_completed(tasks):
                ip = await finished
                if not ip:
                    continue
                try:
                    if ipaddress.IPv4Address(ip).is_global:
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        return ip
                except Exception:
                    continue
        finally:
            await asyncio.gather(*tasks, return_exceptions=True)

    return None


def get_public_ip():
    try:
        ip = asyncio.run(_get_public_ipv4_async())
        if ip:
            return ip
    except RuntimeError:
        pass

    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        resp = sock.getsockname()[0]
        if ipaddress.IPv4Address(resp).is_global:
            return resp
    except (socket.error, IndexError):
        pass
    finally:
        if sock:
            sock.close()

    return "127.0.0.1"


async def _get_public_ipv6_async() -> str | None:
    urls = (
        "http://api6.ipify.org/",
        "http://ipv6.icanhazip.com/",
    )
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [asyncio.ensure_future(_fetch_text(session, url)) for url in urls]
        try:
            for finished in asyncio.as_completed(tasks):
                ip = await finished
                if not ip:
                    continue
                try:
                    if ipaddress.IPv6Address(ip).is_global:
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        return "[%s]" % ip
                except Exception:
                    continue
        finally:
            await asyncio.gather(*tasks, return_exceptions=True)

    return None


def get_public_ipv6():
    try:
        ip = asyncio.run(_get_public_ipv6_async())
        if ip:
            return ip
    except RuntimeError:
        pass

    return "[::1]"


def readable_size(size_bytes):
    if not size_bytes or size_bytes <= 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"
