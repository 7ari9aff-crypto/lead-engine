import pytest

from lead_engine.db import Database
from lead_engine.jobs import (
    COMPLETED, DEGRADED, FAILED, PAUSED, QUEUED, RESUMING, RUNNING,
    IllegalTransition, JobManager,
)


@pytest.fixture()
def jm(tmp_path):
    db = Database(tmp_path / "j.sqlite3")
    return JobManager(db), db


def test_happy_path(jm):
    manager, _ = jm
    job = manager.create_job("v0_saudi_dental")
    assert manager.current(job) == QUEUED
    manager.transition(job, RUNNING)
    manager.transition(job, COMPLETED)
    assert manager.current(job) == COMPLETED


def test_pause_resume_cycle(jm):
    manager, db = jm
    job = manager.create_job("v0_saudi_dental")
    manager.transition(job, RUNNING)
    manager.pause(job, "NO_AVAILABLE_LLM_PROVIDER", "2026-09-10T00:00:00Z")
    assert manager.current(job) == PAUSED
    row = db.one("SELECT resume_at, pause_reason FROM jobs WHERE job_id=?", (job,))
    assert row["pause_reason"] == "NO_AVAILABLE_LLM_PROVIDER"
    assert row["resume_at"] == "2026-09-10T00:00:00Z"
    manager.resume(job)
    assert manager.current(job) == RESUMING
    manager.transition(job, RUNNING)


def test_quota_exhaustion_is_pause_not_failed(jm):
    manager, _ = jm
    job = manager.create_job("icp")
    manager.transition(job, RUNNING)
    manager.transition(job, DEGRADED, "local LLM used")
    manager.transition(job, PAUSED, "NO_AVAILABLE_LLM_PROVIDER")
    assert manager.current(job) == PAUSED
    assert FAILED not in (manager.current(job),)


def test_illegal_transitions_raise(jm):
    manager, _ = jm
    job = manager.create_job("icp")
    with pytest.raises(IllegalTransition):
        manager.transition(job, COMPLETED)          # QUEUED -> COMPLETED
    with pytest.raises(IllegalTransition):
        manager.transition(job, PAUSED)             # QUEUED -> PAUSED
    manager.transition(job, RUNNING)
    manager.transition(job, COMPLETED)
    with pytest.raises(IllegalTransition):
        manager.transition(job, RUNNING)            # COMPLETED is terminal


def test_invalid_job_raises(jm):
    manager, _ = jm
    with pytest.raises(ValueError):
        manager.current("does-not-exist")


def test_events_log(jm):
    manager, db = jm
    job = manager.create_job("icp")
    manager.transition(job, RUNNING)
    manager.transition(job, PAUSED, "NO_AVAILABLE_SEARCH_PROVIDER")
    events = manager.events(job)
    assert [(e["from_state"], e["to_state"]) for e in events] == [
        (QUEUED, RUNNING), (RUNNING, PAUSED)]
