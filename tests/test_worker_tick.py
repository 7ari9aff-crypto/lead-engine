"""Worker tick tests — the unit of durability for queued jobs.

The queue primitives (lease_next/reclaim_expired/...) are Postgres-only SQL
(now(), make_interval, SKIP LOCKED), so these tests fake them and assert the
tick's routing and state-mapping decisions on a real SQLite database. The
queue SQL itself is covered live by tests/test_queue_pg.py.
"""
import json

import pytest

from lead_engine import queue as queue_mod
from lead_engine.db import Database
from lead_engine.jobs import JobManager
from lead_engine.worker import run_worker_tick


class FakeQueue:
    """Records every queue call; returns the configured leased job."""

    def __init__(self, job=None):
        self.job = job
        self.calls = []

    def reclaim_expired(self, db):
        self.calls.append(("reclaim",))
        return 2

    def lease_next(self, db, worker_id, lease_seconds=600):
        self.calls.append(("lease", worker_id, lease_seconds))
        return self.job

    def complete(self, db, job_id):
        self.calls.append(("complete", job_id))

    def release(self, db, job_id):
        self.calls.append(("release", job_id))

    def fail(self, db, job_id, reason):
        self.calls.append(("fail", job_id, reason))
        return "QUEUED"


@pytest.fixture()
def sqldb(tmp_path):
    db = Database(tmp_path / "worker.sqlite3")
    yield db
    db.conn.close()


def leased_job(job_id):
    return {"job_id": job_id, "icp_id": "icp-1", "attempts": 1, "max_attempts": 3}


@pytest.fixture()
def fake_queue(monkeypatch):
    fq = FakeQueue()
    for name in ("reclaim_expired", "lease_next", "complete", "release", "fail"):
        monkeypatch.setattr(queue_mod, name, getattr(fq, name))
    return fq


@pytest.fixture()
def fake_benchmark(monkeypatch):
    calls = []

    def install(summary=None, error=None):
        def run_benchmark(icp, job_id=None, seed_csv=None):
            calls.append(job_id)
            if error:
                raise error
            return (summary or {"state": "COMPLETED"}, None, None)

        monkeypatch.setattr("lead_engine.benchmark.run.run_benchmark", run_benchmark)
        monkeypatch.setattr("lead_engine.config.load_icp",
                            lambda name: {"icp_id": name})
        return calls

    return install


@pytest.fixture()
def fake_research(monkeypatch):
    def install(summary):
        class FakeOrchestrator:
            def __init__(self, db, settings, job_id):
                pass

            def run(self):
                return summary

        monkeypatch.setattr("lead_engine.research.orchestrator.ResearchOrchestrator",
                            FakeOrchestrator)
        return summary

    return install


def test_empty_queue_returns_without_leasing(sqldb, fake_queue):
    result = run_worker_tick(sqldb, "w-1", settings={})
    assert result["reclaimed"] == 2
    assert result["leased"] is False
    assert result["job_id"] is None
    assert fake_queue.calls == [("reclaim",), ("lease", "w-1", 600)]


def test_tick_reaps_stale_agent_runs(monkeypatch, sqldb, fake_queue):

    reap_calls = []
    monkeypatch.setattr("lead_engine.agent_registry.reclaim_stale_runs",
                        lambda db, stale_hours=24: reap_calls.append(db) or 1)
    result = run_worker_tick(sqldb, "w-1", settings={})
    assert result["stale_runs_reaped"] == 1
    assert reap_calls == [sqldb]


def test_pipeline_job_completes(sqldb, fake_queue, fake_benchmark):
    job_id = JobManager(sqldb).create_job("icp-1")
    fake_queue.job = leased_job(job_id)
    fake_benchmark(summary={"state": "COMPLETED", "final_leads": 3})

    result = run_worker_tick(sqldb, "w-1", settings={})

    assert result["leased"] is True
    assert result["job_id"] == job_id
    assert result["state"] == "COMPLETED"
    assert ("complete", job_id) in fake_queue.calls
    assert not any(c[0] in ("fail", "release") for c in fake_queue.calls)


def test_pipeline_job_paused_goes_through_fail_not_complete(sqldb, fake_queue,
                                                            fake_benchmark):
    job_id = JobManager(sqldb).create_job("icp-1")
    fake_queue.job = leased_job(job_id)
    fake_benchmark(summary={"state": "PAUSED",
                            "pause_reason": "NO_AVAILABLE_PROVIDER:search"})

    run_worker_tick(sqldb, "w-1", settings={})

    assert ("fail", job_id, "NO_AVAILABLE_PROVIDER:search") in fake_queue.calls
    assert not any(c[0] == "complete" for c in fake_queue.calls)


def test_research_job_ready_for_review_releases_the_lease(sqldb, fake_queue,
                                                          fake_research):
    job_id = JobManager(sqldb).create_job("icp-1", {"kind": "research"})
    assert json.loads(sqldb.one(
        "SELECT params FROM jobs WHERE job_id=?", (job_id,))["params"])[
        "kind"] == "research"
    fake_queue.job = leased_job(job_id)
    fake_research({"state": "READY_FOR_REVIEW", "stop_reason": "budget"})

    result = run_worker_tick(sqldb, "w-1", settings={})

    assert result["state"] == "READY_FOR_REVIEW"
    assert ("release", job_id) in fake_queue.calls
    assert not any(c[0] in ("complete", "fail") for c in fake_queue.calls)


def test_research_job_paused_fails_the_lease(sqldb, fake_queue, fake_research):
    job_id = JobManager(sqldb).create_job("icp-1", {"kind": "research"})
    fake_queue.job = leased_job(job_id)
    fake_research({"state": "PAUSED", "pause_reason": "budget-exhausted"})

    run_worker_tick(sqldb, "w-1", settings={})

    assert ("fail", job_id, "budget-exhausted") in fake_queue.calls
    assert not any(c[0] == "release" for c in fake_queue.calls)


def test_pipeline_crash_fails_the_lease_and_reports(sqldb, fake_queue,
                                                    fake_benchmark):
    job_id = JobManager(sqldb).create_job("icp-1")
    fake_queue.job = leased_job(job_id)
    fake_benchmark(error=ValueError("boom"))

    result = run_worker_tick(sqldb, "w-1", settings={})

    assert ("fail", job_id, "ValueError: boom") in fake_queue.calls
    assert result["error"] == "ValueError: boom"
    assert result["state"] == "QUEUED"  # FakeQueue.fail retry return
    assert not any(c[0] == "complete" for c in fake_queue.calls)


def test_platform_mode_on_vercel_means_a_worker_exists(monkeypatch):
    from lead_engine.queue import platform_mode

    # Vercel deploys a scheduled worker (vercel.json crons) — jobs must
    # enqueue instead of running inline in a request that can be killed.
    monkeypatch.setenv("VERCEL", "1")
    assert platform_mode() is True
    # explicit opt-out still wins over the platform
    monkeypatch.setenv("LEAD_ENGINE_QUEUE_MODE", "inline")
    assert platform_mode() is False
    # outside Vercel nothing changed
    monkeypatch.delenv("VERCEL")
    monkeypatch.delenv("LEAD_ENGINE_QUEUE_MODE")
    assert platform_mode() is False
