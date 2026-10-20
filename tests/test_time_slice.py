"""E3 regression: a tick must never run past the serverless request limit.

Vercel kills /api/cron/worker at maxDuration (60 s). The orchestrator ran the
whole research loop inside one request, so any job needing more than 60 s was
killed mid-flight (504) and burned one of its max_attempts each time until it
FAILED. A time slice yields the job back to the queue BEFORE the limit,
without counting as an attempt, and the next tick resumes from persisted state.
"""
import json

import pytest

from lead_engine import queue as queue_mod
from lead_engine.db import Database
from lead_engine.jobs import RUNNING, READY_FOR_REVIEW
from lead_engine.research import ResearchJobManager
from lead_engine.research.orchestrator import ResearchOrchestrator
from tests.conftest import seed_control_plane
from tests.test_research_orchestrator import FakeRouter


class Clock:
    """Fake monotonic clock; each reasoning call 'takes' `step` seconds."""

    def __init__(self, step=20.0):
        self.now = 1000.0
        self.step = step

    def __call__(self):
        return self.now


class SlowRouter(FakeRouter):
    def __init__(self, clock, *a, **k):
        super().__init__(*a, **k)
        self.clock = clock

    def route(self, task, payload, **kw):
        out = super().route(task, payload, **kw)
        self.clock.now += self.clock.step
        return out


@pytest.fixture()
def db(tmp_path):
    db = Database(tmp_path / "slice.sqlite3")
    db.org_id = "org-test"
    seed_control_plane(db)
    return db


def _turns(n):
    plan = {"queries": [{"q": "x", "city": "Riyadh", "lang": "en"}],
            "target_candidates": 99, "verify_fields": []}
    turn = {"thought": "t", "done": False, "actions": [], "note": "n"}
    return [plan] + [dict(turn) for _ in range(n)]


def test_loop_yields_before_deadline_and_keeps_state(db):
    clock = Clock(step=20.0)
    router = SlowRouter(clock, _turns(10))
    manager = ResearchJobManager(db)
    job_id = manager.create("slow research")
    orch = ResearchOrchestrator(db, {}, job_id, router=router,
                                deadline=clock.now + 60.0, clock=clock)
    summary = orch.run()

    # stopped on its own, well inside the limit, not at the hard kill
    assert summary.get("yielded") is True
    assert clock.now <= 1000.0 + 60.0
    # state survived for the next slice: plan persisted, steps counted
    ctx = manager.context(job_id)
    assert ctx["plan"]
    assert int(manager.counters(job_id).get("steps") or 0) >= 1
    # NOT finalized: the human gate was not reached on a partial run
    assert manager.jobs.current(job_id) != READY_FOR_REVIEW


def test_no_deadline_keeps_old_behaviour(db):
    # deadline=None must behave exactly as before (CLI worker, tests, API inline)
    router = FakeRouter(_turns(0) + [{"thought": "x", "done": True, "actions": []}])
    manager = ResearchJobManager(db)
    job_id = manager.create("fast research")
    summary = ResearchOrchestrator(db, {}, job_id, router=router).run()
    assert summary["state"] == READY_FOR_REVIEW


def test_yield_slice_requeues_and_refunds_the_attempt(db):
    db.execute("INSERT INTO jobs (job_id, icp_id, state, attempts, max_attempts,"
               " worker_id, lease_expires_at, created_at, updated_at)"
               " VALUES ('j-1','icp','RUNNING',2,3,'w','2999-01-01T00:00:00Z',"
               "'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')")
    queue_mod.yield_slice(db, "j-1")
    row = db.one("SELECT state, attempts, worker_id, lease_expires_at, resume_at"
                 " FROM jobs WHERE job_id='j-1'")
    assert row["state"] == "QUEUED"
    assert row["attempts"] == 1          # the slice is not a failure
    assert row["worker_id"] is None
    assert row["lease_expires_at"] is None
    assert row["resume_at"] is None      # no backoff: continue on the next tick


def test_yield_slice_never_goes_negative(db):
    db.execute("INSERT INTO jobs (job_id, icp_id, state, attempts, max_attempts,"
               " created_at, updated_at) VALUES ('j-2','icp','RUNNING',0,3,"
               "'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')")
    queue_mod.yield_slice(db, "j-2")
    assert db.one("SELECT attempts FROM jobs WHERE job_id='j-2'")["attempts"] == 0
