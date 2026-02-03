from enum import Enum


class Role(str, Enum):
    BACKEND = "backend"
    NODE = "node"
    SCHEDULER = "scheduler"
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
        """All roles except all-in-one need NATS"""
        return self != Role.ALL_IN_ONE
