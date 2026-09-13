"""R3 — agentic orchestrator tests with a scripted fake router.

Covers the loop end-to-end WITHOUT network: planning -> tool rounds (search,
save_fact) -> done -> verification sweep -> qualification from facts ->
READY_FOR_REVIEW. Also: budgets stop, capacity pause, ask_user waiting,
scope enforcement, and the no-send-tool invariant.
"""
import json

import pytest

from lead_engine.db import Database
from lead_engine.jobs import (
    PAUSED, READY_FOR_REVIEW, RUNNING, WAITING_FOR_USER,
)
from lead_engine.research import ResearchJobManager
from lead_engine.research.orchestrator import ResearchOrchestrator
from lead_engine.research.tools import TOOLS, ScopeDenied, ToolContext, execute_tool
from lead_engine.router import NoProviderAvailable
from lead_engine.truth import FactsStore


class FakeRouter:
    """Routes 'reasoning' from a scripted queue; 'web_search'/'email_verify'
    return deterministic fake provider results."""

    def __init__(self, reasoning_script, search_results=None, email_status="DELIVERABLE"):
        self.reasoning_script = list(reasoning_script)
        self.search_results = search_results or []
        self.email_status = email_status
        self.reasoning_payloads = []
        self.search_queries = []

    def route(self, task, payload, job_id=None, use_cache=True,
              cache_data_type=None, prefer_provider=None):
        if task == "reasoning":
            self.reasoning_payloads.append(payload)
            if not self.reasoning_script:
                raise AssertionError("reasoning script exhausted")
            item = self.reasoning_script.pop(0)
            if isinstance(item, Exception):
                raise item
            return {"provider": "gemini", "text": json.dumps(item)}, \
                {"provider": "gemini"}
        if task == "web_search":
            self.search_queries.append(payload["query"])
            return {"provider": "tavily", "results": self.search_results}, \
                {"provider": "tavily"}
        if task == "email_verify":
            return {"provider": "hunter", "status": self.email_status,
                    "confidence": 0.9,
                    "details": {"reason": "smtp_accepted"}}, {"provider": "hunter"}
        raise AssertionError(f"unexpected task {task}")


@pytest.fixture()
def db(tmp_path):
    db = Database(tmp_path / "orch.sqlite3")
    db.org_id = "org-test"
    return db


def _script(db, search_results=None):
    """A realistic 3-turn scenario: search -> save facts -> done, then two
    qualification verdicts for the two candidates."""
    return [
        # plan
        {"queries": [{"q": "dental clinic riyadh", "city": "Riyadh", "lang": "en"}],
         "target_candidates": 2, "verify_fields": ["phone"]},
        # turn 1: search
        {"thought": "ابدأ بالبحث المخطط", "done": False,
         "actions": [{"tool": "search_companies",
                      "args": {"query": "dental clinic riyadh", "city": "Riyadh"}}],
         "note": "جاري البحث"},
        # turn 2: persist what the search taught us
        {"thought": "حفظ الحقائق من النتائج", "done": False,
         "actions": [
             {"tool": "save_fact",
              "args": {"name": "Clinic A", "domain": "clinica-sa.com", "field": "phone",
                       "value": "+966501111111", "source_url": "https://clinica-sa.com",
                       "provider": "tavily", "quote": "call us"}},
             {"tool": "save_fact",
              "args": {"name": "Clinic B", "domain": "clinicb-sa.com", "field": "phone",
                       "value": "+966502222222", "source_url": "https://clinicb-sa.com",
                       "provider": "tavily"}},
         ]},
        # turn 3: coverage reached
        {"thought": "مرشحان يكفيان للهدف", "done": True, "actions": [],
         "note": "اكتملت التغطية"},
        # qualifications (per subject)
        {"fit_score": 82, "tier": "A", "why": ["عيادة في الرياض بمصدر هاتف"],
         "confidence": 0.8, "unknown_fields": ["branches"], "blockers": []},
        {"fit_score": 55, "tier": "B", "why": ["لا يوجد بريد إلكتروني موثق"],
         "confidence": 0.6, "unknown_fields": ["email"], "blockers": []},
    ]


def test_full_loop_reaches_ready_for_review(db):
    script = _script(db)
    router = FakeRouter(script, search_results=[
        {"title": "Clinic A", "url": "https://clinica-sa.com", "snippet": "dental"},
        {"title": "Clinic B", "url": "https://clinicb-sa.com", "snippet": "dental"},
    ])
    manager = ResearchJobManager(db)
    job_id = manager.create("دور على عيادات أسنان في الرياض")
    orch = ResearchOrchestrator(db, {}, job_id, router=router)
    summary = orch.run()

    assert summary["state"] == READY_FOR_REVIEW
    assert summary["stop_reason"] == "OBJECTIVE_SATISFIED"
    assert manager.jobs.current(job_id) == READY_FOR_REVIEW
    counters = manager.counters(job_id)
    assert counters["searches"] == 1
    assert counters["candidates"] == 2
    assert counters["model_calls"] >= 4  # plan + 3 turns
    # facts persisted with provenance
    facts = db.query("SELECT * FROM research_facts WHERE field='phone'")
    assert len(facts) == 2
    assert facts[0]["status"] == "UNVERIFIED"
    # the search tool actually hit the fake search provider
    assert router.search_queries == ["dental clinic riyadh"]
    # an agent run with recorded steps exists for audit
    runs = db.query("SELECT * FROM agent_runs")
    assert len(runs) == 1
    steps = db.query("SELECT * FROM agent_steps ORDER BY id")
    step_names = [s["step_name"] for s in steps]
    assert any(n.startswith("turn:") for n in step_names)
    assert any(n.startswith("tool:search_companies") for n in step_names)
    assert any(n.startswith("qualify:") for n in step_names)


def test_budget_exhaustion_stops_with_reason(db):
    script = [
        {"queries": [], "target_candidates": 100},
        {"thought": "never done", "done": False, "actions": []},
        {"thought": "never done", "done": False, "actions": []},
        {"thought": "never done", "done": False, "actions": []},
    ]
    manager = ResearchJobManager(db)
    job_id = manager.create("objective", budgets={"max_steps": 2, "max_model_calls": 99})
    orch = ResearchOrchestrator(db, {}, job_id, router=FakeRouter(script))
    summary = orch.run()
    assert summary["state"] == READY_FOR_REVIEW
    assert summary["stop_reason"] == "BUDGET_EXHAUSTED"


def test_capacity_pause_on_missing_provider(db):
    script = [NoProviderAvailable("reasoning", tried=["gemini:no_key"])]
    manager = ResearchJobManager(db)
    job_id = manager.create("objective")
    orch = ResearchOrchestrator(db, {}, job_id, router=FakeRouter(script))
    summary = orch.run()
    assert summary["state"] == PAUSED
    job = db.one("SELECT pause_reason FROM jobs WHERE job_id=?", (job_id,))
    assert "NO_CAPACITY:reasoning" in job["pause_reason"]


def test_ask_user_parks_job_in_waiting_for_user(db):
    script = [
        {"queries": [], "target_candidates": 5},
        {"thought": "محتاج توضيح", "done": False,
         "actions": [{"tool": "ask_user",
                      "args": {"question": "أي مدينة أعطيها أولوية؟"}}]},
    ]
    manager = ResearchJobManager(db)
    job_id = manager.create("objective")
    orch = ResearchOrchestrator(db, {}, job_id, router=FakeRouter(script))
    summary = orch.run()
    assert summary["state"] == WAITING_FOR_USER
    assert db.one("SELECT state FROM jobs WHERE job_id=?", (job_id,))["state"] \
        == WAITING_FOR_USER
    # the open question is stored for the resume flow
    assert manager.progress(job_id)["stats"]["open_questions"] == 1


def test_verification_sweep_verifies_email_facts(db):
    script = [
        {"queries": [], "target_candidates": 1},
        {"thought": "حفظ إيميل", "done": False,
         "actions": [{"tool": "save_fact",
                      "args": {"name": "Clinic C", "domain": "clinic-c.com",
                               "field": "email", "value": "dr.salem@clinic-c.com",
                               "source_url": "https://clinic-c.com",
                               "provider": "tavily"}}]},
        {"thought": "خلصنا", "done": True, "actions": []},
        {"fit_score": 70, "tier": "B", "why": ["إيميل موثق"], "confidence": 0.8,
         "unknown_fields": [], "blockers": []},
    ]
    manager = ResearchJobManager(db)
    job_id = manager.create("objective")
    orch = ResearchOrchestrator(db, {}, job_id,
                                router=FakeRouter(script, email_status="DELIVERABLE"))
    summary = orch.run()
    fact = db.one("SELECT * FROM research_facts WHERE field='email'")
    assert fact["status"] == "VERIFIED"
    assert summary["stats"]["verified_facts"] == 1


# ----------------------------------------------------------------- tools
def _ctx(db, job_id, scopes=("search:read", "evidence:write")):
    manager = ResearchJobManager(db)
    return ToolContext(db=db, router=None, store=FactsStore(db), manager=manager,
                       job_id=job_id, allowed_scopes=set(scopes), run_id=None)


def test_scope_enforcement_denies_missing_scope(db):
    manager = ResearchJobManager(db)
    job_id = manager.create("objective")
    ctx = _ctx(db, job_id, scopes=("search:read",))  # no evidence:write
    with pytest.raises(ScopeDenied):
        execute_tool(ctx, "save_fact", {"name": "X", "field": "phone", "value": "1"})


def test_unknown_tool_rejected(db):
    manager = ResearchJobManager(db)
    job_id = manager.create("objective")
    out = execute_tool(_ctx(db, job_id), "make_coffee", {})
    assert "error" in out


def test_no_send_or_human_decision_tools_exist():
    """THE invariant (§31-32): no outreach, no human decision as a tool."""
    forbidden = ("send", "approve", "reject", "outreach", "email_send", "whatsapp")
    for name in TOOLS:
        for bad in forbidden:
            assert bad not in name.lower(), f"forbidden tool registered: {name}"
    assert "APPROVE_CONTACT" not in json.dumps(list(TOOLS))


def test_canonical_subject_collapses_by_domain(db):
    from lead_engine.research.tools import canonical_subject
    assert canonical_subject({"name": "Clinic A", "domain": "https://www.ClinicA.com/x"}) \
        == ("company", "clinica.com")
    kind, subject = canonical_subject({"name": "عيادة النور"})
    assert kind == "company" and subject.startswith("name:")
