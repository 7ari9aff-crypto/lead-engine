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


# ---- finalize must be resumable: qualification is per-subject LLM work -------

def _seed_subjects(db, manager, job_id, n):
    store_rows = []
    from lead_engine.truth import FactsStore
    store = FactsStore(db)
    for i in range(n):
        store.record_fact("company", f"c{i}.example.com", "phone", f"+96650{i:07d}",
                          source_url=f"https://c{i}.example.com", provider="tavily",
                          job_id=job_id)
    return n


def _qual_script(n):
    return [{"fit_score": 70, "tier": "B", "why": ["ok"], "confidence": 0.7,
             "unknown_fields": [], "blockers": []} for _ in range(n)]


def test_finalize_yields_mid_qualification_and_resumes_without_redoing_work(db):
    clock = Clock(step=4.0)           # each qualification costs 4 "seconds"
    manager = ResearchJobManager(db)
    job_id = manager.create("many subjects")
    manager.set_plan(job_id, {"queries": [], "target_candidates": 1})
    n = _seed_subjects(db, manager, job_id, 12)
    manager.jobs.transition(job_id, RUNNING)

    router = SlowRouter(clock, _qual_script(40))
    orch = ResearchOrchestrator(db, {}, job_id, router=router,
                                deadline=clock.now + 30.0, clock=clock)
    run_id = orch._ensure_agent_run()
    first = orch._finalize(run_id)

    # stopped inside the limit, did NOT reach the review gate on a partial pass
    assert first.get("yielded") is True
    assert clock.now <= 1000.0 + 30.0
    done_first = len(router.reasoning_payloads)
    assert 0 < done_first < n

    # next slice: fresh clock/deadline, same persisted state
    clock2 = Clock(step=4.0)
    router2 = SlowRouter(clock2, _qual_script(40))
    orch2 = ResearchOrchestrator(db, {}, job_id, router=router2,
                                 deadline=clock2.now + 300.0, clock=clock2)
    second = orch2._finalize(orch2._ensure_agent_run())

    assert second.get("yielded") is not True
    assert manager.jobs.current(job_id) == READY_FOR_REVIEW
    # exactly n model calls in total: nothing was qualified twice
    assert done_first + len(router2.reasoning_payloads) == n
    leads = db.query("SELECT lead_id FROM leads")
    assert len(leads) == n


def test_resumed_job_goes_straight_to_finalize_and_keeps_its_stop_reason(db):
    """Slice 1 ends mid-finalize after a BUDGET stop. Slice 2 enters via run():
    it must not re-run the discovery loop, and must still report the budget stop
    instead of silently relabelling it COVERAGE_ADEQUATE."""
    clock = Clock(step=4.0)
    manager = ResearchJobManager(db)
    job_id = manager.create("resume me")
    manager.set_plan(job_id, {"queries": [], "target_candidates": 1})
    _seed_subjects(db, manager, job_id, 8)
    manager.jobs.transition(job_id, RUNNING)
    manager.set_state(job_id, "_stop", ["BUDGET_EXHAUSTED", "max_steps: {}"])
    manager.set_state(job_id, "_finalizing", True)

    router = SlowRouter(clock, _qual_script(20))       # NO discovery turns scripted
    summary = ResearchOrchestrator(db, {}, job_id, router=router,
                                   deadline=clock.now + 300.0, clock=clock).run()

    assert summary.get("yielded") is not True
    assert manager.jobs.current(job_id) == READY_FOR_REVIEW
    assert len(router.reasoning_payloads) == 8          # only qualifications
    assert manager.context(job_id)["stop_reason"] == "BUDGET_EXHAUSTED"


def test_review_gate_clears_resume_markers(db):
    """A job reopened after review (READY_FOR_REVIEW -> RUNNING) must start from a
    clean slate, not jump into finalize on stale verdicts."""
    clock = Clock(step=1.0)
    manager = ResearchJobManager(db)
    job_id = manager.create("reopen me")
    manager.set_plan(job_id, {"queries": [], "target_candidates": 1})
    _seed_subjects(db, manager, job_id, 3)
    manager.jobs.transition(job_id, RUNNING)

    router = SlowRouter(clock, _qual_script(10))
    ResearchOrchestrator(db, {}, job_id, router=router,
                         deadline=clock.now + 300.0, clock=clock).run()

    assert manager.jobs.current(job_id) == READY_FOR_REVIEW
    for key in ("_finalizing", "_verdicts", "_stop"):
        assert manager.get_state(job_id, key) is None, f"{key} survived the gate"
