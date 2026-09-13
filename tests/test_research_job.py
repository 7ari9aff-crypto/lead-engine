"""R2 — persistent research jobs: extended state machine, budgets, stop
reasons, cancellation, and the legacy-path compatibility guarantee."""
import pytest

from lead_engine.db import Database
from lead_engine.jobs import (
    CANCELLED, COMPLETED, FAILED, IllegalTransition, PAUSED, QUEUED,
    READY_FOR_REVIEW, RESUMING, RUNNING, WAITING_FOR_USER, JobManager,
)
from lead_engine.research import ResearchJobManager


@pytest.fixture()
def db(tmp_path):
    db = Database(tmp_path / "r.sqlite3")
    db.org_id = "org-test"
    return db


@pytest.fixture()
def manager(db):
    return ResearchJobManager(db)


def test_create_starts_queued_with_context(manager):
    job_id = manager.create("دور على عيادات أسنان في جدة")
    assert manager.jobs.current(job_id) == QUEUED
    ctx = manager.context(job_id)
    assert ctx["objective"] == "دور على عيادات أسنان في جدة"
    assert ctx["kind"] == "research"
    assert ctx["budgets"]["max_searches"] > 0
    assert ctx["counters"] == {}
    assert manager.is_research(job_id)


def test_create_requires_objective(manager):
    with pytest.raises(ValueError):
        manager.create("   ")


def test_budget_override_per_job(db):
    mgr = ResearchJobManager(db, settings={"research": {"max_searches": 7}})
    job_id = mgr.create("objective")
    assert mgr.context(job_id)["budgets"]["max_searches"] == 7
    job2 = mgr.create("objective", budgets={"max_steps": 3})
    assert mgr.context(job2)["budgets"]["max_steps"] == 3
    assert mgr.context(job2)["budgets"]["max_searches"] == 7  # defaults survive


def test_phase_cycle_to_ready_for_review(manager):
    job_id = manager.create("objective")
    manager.jobs.transition(job_id, RUNNING)
    manager.set_phase(job_id, "DISCOVERING")
    manager.set_phase(job_id, "RESEARCHING")
    manager.set_phase(job_id, "VERIFYING")
    manager.set_phase(job_id, "QUALIFYING")
    manager.ready_for_review(job_id, "OBJECTIVE_SATISFIED", "47 fits")
    assert manager.jobs.current(job_id) == READY_FOR_REVIEW
    ctx = manager.context(job_id)
    assert ctx["stop_reason"] == "OBJECTIVE_SATISFIED"
    assert ctx["stop_detail"] == "47 fits"
    manager.complete(job_id)
    assert manager.jobs.current(job_id) == COMPLETED


def test_ready_for_review_can_return_to_running_research_more(manager):
    job_id = manager.create("objective")
    manager.jobs.transition(job_id, RUNNING)
    manager.ready_for_review(job_id, "USER_STOPPED")
    manager.jobs.transition(job_id, RUNNING)  # RESEARCH_MORE resumes the loop
    assert manager.jobs.current(job_id) == RUNNING


def test_illegal_research_transitions(manager):
    job_id = manager.create("objective")
    with pytest.raises(IllegalTransition):
        manager.jobs.transition(job_id, READY_FOR_REVIEW)  # QUEUED -> ready
    manager.jobs.transition(job_id, RUNNING)
    manager.ready_for_review(job_id, "BUDGET_EXHAUSTED")
    manager.complete(job_id)
    with pytest.raises(IllegalTransition):
        manager.jobs.transition(job_id, RUNNING)  # COMPLETED terminal


def test_waiting_for_user_blocks_then_resumes(manager):
    job_id = manager.create("objective")
    manager.jobs.transition(job_id, RUNNING)
    manager.waiting_for_user(job_id, "أي مدينة أعطيها أولوية؟")
    assert manager.jobs.current(job_id) == WAITING_FOR_USER
    manager.jobs.transition(job_id, RUNNING)
    assert manager.jobs.current(job_id) == RUNNING


def test_capacity_pause_maps_to_paused_and_resumes(manager):
    job_id = manager.create("objective")
    manager.jobs.transition(job_id, RUNNING)
    manager.pause_for_capacity(job_id, "NO_AVAILABLE_PROVIDER:search",
                               "2026-09-13T12:00:00Z")
    assert manager.jobs.current(job_id) == PAUSED
    manager.jobs.resume(job_id)
    assert manager.jobs.current(job_id) == RESUMING
    manager.jobs.transition(job_id, RUNNING)


def test_cancel_from_live_state(manager):
    job_id = manager.create("objective")
    manager.jobs.transition(job_id, RUNNING)
    manager.set_phase(job_id, "RESEARCHING")
    manager.cancel(job_id, by="hosam")
    assert manager.jobs.current(job_id) == CANCELLED
    ctx = manager.context(job_id)
    assert ctx["stop_reason"] == "USER_STOPPED"
    with pytest.raises(IllegalTransition):
        manager.jobs.transition(job_id, RUNNING)  # CANCELLED terminal


def test_budget_check_exceeds_and_reports(manager):
    job_id = manager.create("objective", budgets={"max_searches": 2})
    manager.bump_counter(job_id, "searches")
    ok, exceeded, snap = manager.budget_check(job_id)
    assert ok and exceeded is None
    manager.bump_counter(job_id, "searches")
    ok, exceeded, snap = manager.budget_check(job_id)
    assert not ok
    assert exceeded == "max_searches"
    assert snap["searches"]["used"] == 2
    assert snap["searches"]["limit"] == 2


def test_counters_accumulate(manager):
    job_id = manager.create("objective")
    manager.bump_counter(job_id, "tool_calls")
    manager.bump_counter(job_id, "tool_calls", 2)
    assert manager.counters(job_id)["tool_calls"] == 3


def test_progress_narration_payload(manager, db):
    from lead_engine.truth import FactsStore

    job_id = manager.create("objective")
    store = FactsStore(db)
    store.record_fact("company", "org:c.com", "phone", "1",
                      source_url="https://a.com", provider="tavily", job_id=job_id)
    store.record_fact("company", "org:c.com", "phone", "2",
                      source_url="https://b.com", provider="brave", job_id=job_id)
    store.add_visit(job_id, "https://c.com")
    progress = manager.progress(job_id)
    assert progress["state"] == QUEUED
    assert progress["stats"]["all_facts"] == 2
    assert progress["stats"]["open_conflicts"] == 1
    assert progress["stats"]["visited_sources"] == 1
    assert "searches" in progress["budgets"]


def test_research_more_chains_parent(manager):
    parent = manager.create("parent objective")
    child = manager.create("نفس الهدف — عمق أكبر", parent_job_id=parent)
    assert manager.context(child)["parent_job_id"] == parent


def test_legacy_job_path_unaffected(db):
    """The deterministic pipeline keeps its exact semantics (§35: never break
    the existing path)."""
    jm = JobManager(db)
    job_id = jm.create_job("v0_saudi_dental")
    assert not ResearchJobManager(db).is_research(job_id)
    jm.transition(job_id, RUNNING)
    jm.transition(job_id, COMPLETED)
    assert jm.current(job_id) == COMPLETED
