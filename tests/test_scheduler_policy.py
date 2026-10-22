from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.executors.base import run_job
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import ValidationError

from app.scheduler import scheduler
from config import JobSettings, job_settings


def make_job(callback, grace=None):
    isolated = AsyncIOScheduler(job_defaults=scheduler._job_defaults, timezone="UTC")
    # A paused scheduler materializes job defaults without starting any job.
    isolated.start(paused=True)
    kwargs = {} if grace is None else {"misfire_grace_time": grace}
    return isolated, isolated.add_job(callback, "interval", seconds=10, **kwargs)


@pytest.mark.asyncio
async def test_scheduler_defaults_are_bounded_and_coalesced():
    isolated, job = make_job(MagicMock())
    try:
        assert job.max_instances == 1
        assert job.coalesce is True
        assert job.misfire_grace_time == job_settings.misfire_grace_time
    finally:
        isolated.shutdown(wait=False)


@pytest.mark.asyncio
async def test_recent_misfire_executes_but_old_one_is_reported():
    callback = MagicMock()
    isolated, job = make_job(callback, grace=60)
    try:
        events = run_job(job, "default", [datetime.now(UTC) - timedelta(seconds=5)], "test-scheduler")
        assert events[0].code == EVENT_JOB_EXECUTED
        callback.assert_called_once()
        callback.reset_mock()
        events = run_job(job, "default", [datetime.now(UTC) - timedelta(seconds=120)], "test-scheduler")
        assert events[0].code == EVENT_JOB_MISSED
        callback.assert_not_called()
    finally:
        isolated.shutdown(wait=False)


@pytest.mark.asyncio
async def test_job_explicit_policy_is_preserved():
    isolated, job = make_job(MagicMock(), grace=5)
    try:
        assert job.misfire_grace_time == 5
    finally:
        isolated.shutdown(wait=False)


def test_misfire_grace_must_be_positive():
    with pytest.raises(ValidationError):
        JobSettings(_env_file=None, JOB_MISFIRE_GRACE_TIME=0)


@pytest.mark.asyncio
async def test_delayed_interval_is_coalesced_to_one_submission(monkeypatch):
    from apscheduler.schedulers.base import STATE_RUNNING

    isolated, job = make_job(MagicMock())
    executor = MagicMock()
    monkeypatch.setattr(isolated, "_lookup_executor", lambda _: executor)
    now = datetime.now(UTC)
    isolated.modify_job(job.id, next_run_time=now - timedelta(seconds=35))
    try:
        isolated.state = STATE_RUNNING
        isolated._process_jobs()
        executor.submit_job.assert_called_once()
        run_times = executor.submit_job.call_args.args[1]
        assert len(run_times) == 1
        assert run_times[0] == now - timedelta(seconds=5)
    finally:
        isolated.shutdown(wait=False)


def test_misfire_grace_can_be_configured(monkeypatch):
    monkeypatch.setenv("JOB_MISFIRE_GRACE_TIME", "120")
    assert JobSettings(_env_file=None).misfire_grace_time == 120


@pytest.mark.parametrize("name", list(JobSettings.model_fields))
@pytest.mark.parametrize("invalid", [0, -1])
def test_all_scheduler_intervals_reject_nonpositive_values(name, invalid):
    alias = JobSettings.model_fields[name].validation_alias
    with pytest.raises(ValidationError):
        JobSettings(_env_file=None, **{alias: invalid})
