from enum import Enum


class Role(str, Enum):
    BACKEND = "backend"  # deprecated: remove in 7.0.0
    NODE = "node"  # deprecated: remove in 7.0.0
    SCHEDULER = "scheduler"  # deprecated: remove in 7.0.0
    ALL_IN_ONE = "all-in-one"

    @property
    def runs_panel(self):
        """HTTP server + dashboard + API routes"""
        return self in (Role.BACKEND, Role.ALL_IN_ONE)

    @property
    def runs_node(self):
        """Node worker service + node-related jobs"""
        return self in (Role.NODE, Role.ALL_IN_ONE)

    @property
    def runs_scheduler(self):
        """Scheduler jobs + notification dispatcher"""
        return self in (Role.SCHEDULER, Role.ALL_IN_ONE)

    @property
    def requires_nats(self):
        """Split roles always need NATS; all-in-one needs it when UVICORN_WORKERS>1."""
        return self != Role.ALL_IN_ONE

    @property
    def is_deprecated(self) -> bool:
        """True for roles scheduled for removal in 7.0.0."""
        return self in (Role.BACKEND, Role.NODE, Role.SCHEDULER)
