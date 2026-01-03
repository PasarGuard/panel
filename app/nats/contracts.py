import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

PANEL_JOBS_SUBJECT = "panel.jobs.>"
PANEL_EVENTS_SUBJECT = "panel.events.>"


class JobType(str, Enum):
    """Canonical job types for panel + worker + node."""

    USER_CREATE = "panel.jobs.user.create"
    USER_UPDATE = "panel.jobs.user.update"
    USER_DELETE = "panel.jobs.user.delete"
    USER_RESET_USAGE = "panel.jobs.user.reset_usage"
    USER_SUBSCRIPTION_REBUILD = "panel.jobs.subscriptions.rebuild"

    NODE_APPLY_CONFIG = "panel.jobs.node.apply_config"
    NODE_RESTART = "panel.jobs.node.restart"
    NODE_SYNC_USERS = "panel.jobs.node.sync_users"
    NODE_STATS_REFRESH = "panel.jobs.node.refresh_stats"

    NOTIFICATION_FLUSH = "panel.jobs.notifications.flush"
    ANALYTICS_AGGREGATE = "panel.jobs.analytics.aggregate"
    SCHEDULED_TASK = "panel.jobs.scheduled.execute"


class EventType(str, Enum):
    """Common event types emitted by workers/nodes."""

    JOB_STARTED = "panel.events.job.started"
    JOB_COMPLETED = "panel.events.job.completed"
    JOB_FAILED = "panel.events.job.failed"
    NODE_STATUS = "panel.events.node.status"
    NODE_METRICS = "panel.events.node.metrics"
    AUDIT = "panel.events.audit"


class JobStatus(str, Enum):
    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"


class JobMessage(BaseModel):
    """Envelope used for all job publications."""

    job_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str | None = None
    requested_by: dict[str, Any] | None = None
    idempotency_key: str | None = None
    retries: int = 0
    timeout: float | None = None
    reply_to: str | None = None

    @property
    def msg_id(self) -> str:
        """Preferred message id for deduplication."""
        return self.idempotency_key or self.job_id


class JobResult(BaseModel):
    """Result payload emitted by workers."""

    job_id: str
    type: str
    status: JobStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str | None = None
    attempt: int = 1


def build_job_message(
    job_type: JobType | str,
    payload: dict[str, Any],
    *,
    requested_by: dict[str, Any] | None = None,
    trace_id: str | None = None,
    idempotency_key: str | None = None,
    timeout: float | None = None,
    reply_to: str | None = None,
) -> JobMessage:
    """Convenience helper to create a ready-to-send job message."""
    return JobMessage(
        type=str(job_type),
        payload=payload,
        requested_by=requested_by,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
        timeout=timeout,
        reply_to=reply_to,
    )


__all__ = [
    "EventType",
    "JobMessage",
    "JobResult",
    "JobStatus",
    "JobType",
    "PANEL_EVENTS_SUBJECT",
    "PANEL_JOBS_SUBJECT",
    "build_job_message",
]
