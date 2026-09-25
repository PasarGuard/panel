from __future__ import annotations

import time
from contextvars import ContextVar

_phases: ContextVar[dict[str, float] | None] = ContextVar("request_performance_phases", default=None)


def start_request_phases() -> None:
    _phases.set({})


def record_phase(name: str, duration_ms: float) -> None:
    phases = _phases.get()
    if phases is not None:
        phases[name] = round(duration_ms, 2)


def request_phases() -> dict[str, float]:
    return dict(_phases.get() or {})


class phase:
    def __init__(self, name: str):
        self.name = name
        self.started = 0.0

    def __enter__(self):
        self.started = time.perf_counter()
        return self

    def __exit__(self, *_exc):
        record_phase(self.name, (time.perf_counter() - self.started) * 1000)
        return False
