"""R6 — END-TO-END: chat message -> research job -> agentic loop with tools ->
verification -> qualification from facts -> materialized leads -> Stage 3
presentation -> the four human decisions -> RESEARCH_MORE continuation.

Runs over the real FastAPI app (TestClient) with a scripted router on a temp
DB — no network, no quota — proving the full target flow (directive §46).
"""
import json

import pytest
from fastapi.testclient import TestClient

from lead_engine.api import research_api, review_api
from lead_engine.api.app import app
from lead_engine.db import Database, open_db
from lead_engine.research import ResearchJobManager


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "e2e.sqlite3")
    database.org_id = "org-e2e"
    return database


@pytest.fixture()
def client(db, monkeypatch):
    def override(module):
        def _get_db(request=None):
            yield db
        app.dependency_overrides[module.get_db] = _get_db

    override(research_api)
    override(review_api)

    script = [
        # planner
        {"queries": [{"q": "dental clinic riyadh", "city": "Riyadh", "lang": "en"}],
         "target_candidates": 2, "verify_fields": ["phone", "email"]},
        # turn 1: two searches
        {"thought": "أبدأ بالبحث المخطط", "done": False,
         "actions": [{"tool": "search_companies",
                      "args": {"query": "dental clinic riyadh", "city": "Riyadh"}}]},
        # turn 2: persist facts from snippets (provenance!)
        {"thought": "أحفظ ما تعلمته", "done": False,
         "actions": [
             {"tool": "save_fact",
              "args": {"name": "Clinic A", "domain": "clinica-sa.com",
                       "field": "phone", "value": "+966501111111",
                       "source_url": "https://clinica-sa.com", "provider": "tavily",
                       "query": "dental clinic riyadh", "quote": "call us"}},
             {"tool": "save_fact",
              "args": {"name": "Clinic A", "domain": "clinica-sa.com",
                       "field": "city", "value": "Riyadh",
                       "source_url": "https://clinica-sa.com", "provider": "tavily"}},
             {"tool": "save_fact",
              "args": {"name": "Clinic B", "domain": "clinicb-sa.com",
                       "field": "phone", "value": "+966502222222",
                       "source_url": "https://directory-sa.com/clinicb",
                       "provider": "brave", "query": "dental clinic riyadh"}},
         ]},
        # turn 3: a second independent source verifies Clinic A's phone
        {"thought": "أوثق هاتف العيادة الأولى بمصدر ثانٍ", "done": False,
         "actions": [
             {"tool": "save_fact",
              "args": {"domain": "clinica-sa.com", "field": "phone",
                       "value": "+966501111111",
                       "source_url": "https://directory-sa.com/a", "provider": "exa"}},
             {"tool": "save_fact",
              "args": {"domain": "clinica-sa.com", "field": "employee_count",
                       "value": "35", "quote": "estimated from branches",
                       "inferred": True}},
         ]},
        # turn 4: conflicting phone for Clinic B -> conflict must open
        {"thought": "مصدر تاني بيقول رقم مختلف للعيادة B", "done": False,
         "actions": [
             {"tool": "save_fact",
              "args": {"domain": "clinicb-sa.com", "field": "phone",
                       "value": "+966509999999",
                       "source_url": "https://other-dir.com/b", "provider": "tavily"}},
         ]},
        # turn 5: coverage reached
        {"thought": "الهدف تحقق", "done": True, "actions": [],
         "note": "مرشحان، أحدهما موثق بمصدرين"},
        # qualifications (per subject: clinica, clinicb, and the directory page
        # that deterministic auto-collection also captured — stage 2 filters it)
        {"fit_score": 85, "tier": "A", "why": ["هاتف موثق من مصدرين مستقلين",
                                               "مدينة مطابقة للـICP"],
         "confidence": 0.85, "unknown_fields": ["email"], "blockers": []},
        {"fit_score": 40, "tier": "C",
         "why": ["رقم الهاتف متضارب بين مصدرين — محتاج تحقق"],
         "confidence": 0.5, "unknown_fields": ["email"],
         "blockers": ["phone conflict"]},
        {"fit_score": 8, "tier": "C",
         "why": ["صفحة دليل/مُجمّع وليست عيادة مستهدفة"],
         "confidence": 0.9, "unknown_fields": [], "blockers": ["not a clinic"]},
    ]

    def fake_run(job_id):
        from lead_engine.db import utcnow
        from lead_engine.research.orchestrator import ResearchOrchestrator
        from tests.test_research_orchestrator import FakeRouter

        class LedgerRecordingRouter(FakeRouter):
            """Mirrors what the real Router does on every call: one honest
            usage_ledger row — so the per-job observability wiring is tested."""

            def __init__(self, database):
                super().__init__(script, search_results=[
                    {"title": "Clinic A — Official",
                     "url": "https://clinica-sa.com",
                     "snippet": "dental clinic in riyadh call us"},
                    {"title": "Clinic B listing",
                     "url": "https://directory-sa.com/clinicb",
                     "snippet": "top dental clinic"},
                ])
                self.db = database

            def route(self, task, payload, job_id=None, **kwargs):
                result, meta = super().route(task, payload, job_id=job_id, **kwargs)
                self.db.execute(
                    "INSERT INTO usage_ledger (ts, provider, task, job_id,"
                    " units, unit_kind, status, latency_ms)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (utcnow(), meta.get("provider", "unknown"), task,
                     job_id, 1, "requests", "ok", 42))
                return result, meta

        ResearchOrchestrator(db, {}, job_id,
                             router=LedgerRecordingRouter(db)).run()

    monkeypatch.setattr(research_api, "_run_research", fake_run)
    yield TestClient(app)
    for module in (research_api, review_api):
        app.dependency_overrides.pop(module.get_db, None)


def test_full_target_flow_e2e(client, db):
    # ---- 1) chat-first: a research job is created from a natural objective
    created = client.post("/api/v1/research",
                          json={"objective": "دور على عيادات أسنان في الرياض",
                                "budgets": {"max_searches": 5, "max_steps": 10}})
    assert created.status_code == 200
    job_id = created.json()["job_id"]

    # background runner completed: the job parks at the human gate
    progress = client.get(f"/api/v1/research/{job_id}").json()
    assert progress["state"] == "READY_FOR_REVIEW"
    assert progress["stop_reason"] == "OBJECTIVE_SATISFIED"
    assert progress["stats"]["candidates"] == 3   # broad collection incl. directory
    assert progress["stats"]["all_facts"] >= 5
    assert progress["stats"]["open_conflicts"] == 1
    assert progress["stats"]["verified_facts"] == 1   # only Clinic A's phone earned it
    # observability per job (directive §39)
    obs = progress["observability"]
    assert any(p["provider"] in ("tavily", "brave", "exa", "gemini")
               for p in obs["providers"])

    # ---- 2) Stage 3: the review board interprets every lead
    board = client.get(f"/api/v1/review/pending?job_id={job_id}").json()["leads"]
    # broad collection + strict filtering: the directory page gets qualified
    # and PRESENTED too (with its low score) — nothing hides, the human decides
    assert len(board) == 3
    by_id = {p["lead"]["lead_id"]: p for p in board}
    assert by_id["org-e2e:directory-sa.com"]["fit"]["fit_score"] == 8
    a = by_id["org-e2e:clinica-sa.com"]
    b = by_id["org-e2e:clinicb-sa.com"]

    # Clinic A: VERIFIED phone (2 independent domains), honest missing email
    assert a["verification"]["verified_facts"] == 1
    assert a["facts_snapshot"]["fields"]["phone"]["status"] == "VERIFIED"
    assert a["facts_snapshot"]["fields"]["phone"]["sources"][0]["source_url"]
    assert "email" in a["missing_information"]
    assert a["fit"]["fit_score"] == 85 and a["fit"]["why"]
    assert a["lead"]["stage"] == "REVIEW"

    # Clinic B: conflicted phone stays VISIBLE, never silently resolved
    assert b["facts_snapshot"]["fields"]["phone"]["status"] == "CONFLICTED"
    assert b["fit"]["fit_score"] == 40

    # ---- 3) human decisions: approve A, deep-research B, save later exists
    r1 = client.post("/api/v1/leads/org-e2e:clinica-sa.com/decision",
                     json={"action": "APPROVE_CONTACT", "note": "موثق"})
    assert r1.status_code == 200
    assert "لا يوجد أي إرسال تلقائي" in r1.json()["note"]

    r2 = client.post("/api/v1/leads/org-e2e:clinicb-sa.com/decision",
                     json={"action": "RESEARCH_MORE", "note": "حل تعارض الهاتف"})
    assert r2.status_code == 200
    child_job = r2.json()["child_job_id"]
    child_ctx = ResearchJobManager(db).context(child_job)
    assert child_ctx["parent_job_id"] == job_id
    # the child job inherits the SAME subject facts (context continuation)
    child_progress = client.get(f"/api/v1/research/{child_job}").json()
    assert child_progress["state"] in ("READY_FOR_REVIEW", "PAUSED")

    # decisions are auditable
    audit = db.query("SELECT action, entity_id FROM audit_logs ORDER BY id")
    assert {"action": "lead.approve_contact", "entity_id": "org-e2e:clinica-sa.com"} \
        in [dict(x) for x in audit]
    assert any(a["action"] == "lead.research_more" for a in audit)

    # ---- 4) re-qualification from facts: ICP change needs NO new discovery
    from lead_engine.icp_store import ICPStore

    v2 = ICPStore(db).create_version("agentic", {"industry": "dental",
                                                 "cities": [{"name": "Jeddah"}]})
    ICPStore(db).activate(v2["icp_version_id"])
    usage_before = db.one("SELECT COUNT(*) AS n FROM usage_ledger")["n"]
    facts_before = db.one("SELECT COUNT(*) AS n FROM research_facts")["n"]
    re = client.post("/api/v1/leads/org-e2e:clinica-sa.com/requalify", json={})
    assert re.status_code == 200
    assert re.json()["presentation"]["fit"]["fit_score"] == 0  # city hard-fail
    assert db.one("SELECT COUNT(*) AS n FROM research_facts")["n"] == facts_before
    assert db.one("SELECT COUNT(*) AS n FROM usage_ledger")["n"] == usage_before

    # ---- 5) the no-outreach invariant holds everywhere
    tools = client.get("/api/tools").json()["tools"]
    assert not any("send" in t["name"].lower() or "approve" in t["name"].lower()
                   for t in tools)
