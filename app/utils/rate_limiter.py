import time
from collections import defaultdict
from fastapi import HTTPException, Request, status


class InMemoryRateLimiter:
    """Lightweight sliding-window rate limiter backed by in-memory dict.

    Not suitable for multi-process deployments (use Redis there), but
    protects against brute-force token scanning for single-process or
    per-process workloads (which is the default PasarGuard deployment).
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # key -> list of timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, timestamps: list[float], now: float) -> list[float]:
        cutoff = now - self.window_seconds
        return [t for t in timestamps if t > cutoff]

    def check(self, key: str) -> None:
        now = time.monotonic()
        timestamps = self._requests[key]
        timestamps = self._cleanup(timestamps, now)
        self._requests[key] = timestamps
        if len(timestamps) >= self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )
        timestamps.append(now)


_rate_limiter = InMemoryRateLimiter(max_requests=30, window_seconds=60)


def rate_limit_dependency(request: Request) -> None:
    """FastAPI dependency that rate-limits by client IP."""
    client_ip = request.client.host if request.client else "unknown"
    _rate_limiter.check(client_ip)
