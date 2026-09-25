"""R5 — Stage 3 tests: lead materialization, presentation payload, the four
human decisions, RESEARCH_MORE context continuation, and re-qualification
from stored facts (no re-discovery)."""
import json

import pytest
from fastapi.testclient import TestClient

from lead_engine.api import icp_api, research_api, review_api
from lead_engine.api.app import app
from lead_engine.db import Database
from lead_engine.research import ResearchJobManager
from lead_engine.truth import FactsStore
from tests.conftest import seed_control_plane
from tests.test_research_orchestrator import FakeRouter


@pytest.fixture()
def db(tmp_path):
    db = Database(tmp_path / "stage3.sqlite3")
    db.org_id = "org-test"
    # Research runs behind these paths resolve their agent from seeded rows.
    seed_control_plane(db)
    return db


def _run_research_job(db, extra_script=None):
    """Drive one full research job to READY_FOR_REVIEW with a scripted router."""
    script = [
        {"queries": [{"q": "dental riyadh"}], "target_candidates": 2,
         "verify_fields": ["phone"]},
        {"thought": "بحث", "done": False,
         "actions": [{"tool": "search_companies",
                      "args": {"query": "dental riyadh", "city": "Riyadh"}}]},
        {"thought": "حفظ", "done": False,
         "actions": [
             {"tool": "save_fact",
              "args": {"name": "Clinic A", "domain": "clinica-sa.com",
                       "field": "phone", "value": "+966501111111",
                       "source_url": "https://clinica-sa.com", "provider": "tavily"}},
             {"tool": "save_fact",
              "args": {"name": "Clinic A", "domain": "clinica-sa.com",
                       "field": "city", "value": "Riyadh",
                       "source_url": "https://clinica-sa.com", "provider": "tavily"}},
             {"tool": "save_fact",
              "args": {"domain": "clinica-sa.com",
                       "field": "city", "value": "Riyadh",
                       "source_url": "https://directory-sa.com/a", "provider": "exa"}},
         ]},
        {"thought": "خلصنا", "done": True, "actions": []},
        {"fit_score": 82, "tier": "A",
         "why": ["عيادة في الرياض", "هاتف موثق بمصدر"],
         "confidence": 0.8, "unknown_fields": ["email"], "blockers": []},
    ] + (extra_script or [])
    manager = ResearchJobManager(db)
    job_id = manager.create("دور على عيادات في الرياض")
    from lead_engine.research.orchestrator import ResearchOrchestrator

    ResearchOrchestrator(db, {}, job_id,
                         router=FakeRouter(script, search_results=[
                             {"title": "Clinic A", "url": "https://clinica-sa.com",
                              "snippet": "dental clinic riyadh"},
                         ])).run()
    return job_id


# ------------------------------------------------------- materialization
def test_research_leads_materialize_with_verdict(db):
    _run_research_job(db)
    leads = db.query("SELECT * FROM leads WHERE job_id LIKE '%'")
    assert len(leads) == 1
    lead = leads[0]
    assert lead["lead_id"] == "org-test:clinica-sa.com"
    assert lead["stage"] == "REVIEW"                    # human gate decides
    assert lead["qualification_score"] == 82
    assert lead["tier"] == "A"
    # the verdict travels inside raw for the presentation layer
    raw = json.loads(lead["raw"])
    assert raw["pipeline"]["qualification"]["fit_score"] == 82
    assert raw["pipeline"]["qualification"]["why"]


# --------------------------------------------------------- presentation
def test_presentation_payload_shape(db):
    _run_research_job(db)
    lead = db.one("SELECT * FROM leads")
    from lead_engine.research.presentation import build_presentation

    payload = build_presentation(db, lead)
    assert payload["subject"] == {"kind": "company", "id": "clinica-sa.com"}
    assert payload["fit"]["fit_score"] == 82
    assert payload["fit"]["why"] == ["عيادة في الرياض", "هاتف موثق بمصدر"]
    # honest knowledge state: only the twice-sourced city is VERIFIED; the
    # single-source phone stays UNVERIFIED — nothing claims what it did not earn
    assert payload["verification"]["verified_facts"] == 1
    assert payload["facts_snapshot"]["fields"]["city"]["status"] == "VERIFIED"
    assert payload["facts_snapshot"]["fields"]["phone"]["status"] == "UNVERIFIED" 
    assert "email" in payload["missing_information"]     # honest gaps
    assert payload["identity"]["city"]["value"] == "Riyadh"
    assert payload["lead"]["stage"] == "REVIEW"
    # every fact surfaced carries its provenance
    for node in payload["facts_snapshot"]["fields"].values():
        assert isinstance(node["sources"], list)


# -------------------------------------------------------------- decisions
@pytest.fixture()
def client(db, monkeypatch):
    def override(module):
        def _get_db(request=None):
            yield db
        app.dependency_overrides[module.get_db] = _get_db

    override(research_api)
    override(review_api)
    override(icp_api)

    def fake_run(job_id):
        from lead_engine.config import load_settings
        from lead_engine.research.orchestrator import ResearchOrchestrator

        ResearchOrchestrator(db, load_settings(), job_id).run()

    monkeypatch.setattr(research_api, "_run_research", fake_run)
    yield TestClient(app)
    for module in (research_api, review_api, icp_api):
        app.dependency_overrides.pop(module.get_db, None)


def test_four_decisions_flow(client, db):
    _run_research_job(db)
    lead = db.one("SELECT * FROM leads")
    lead_id = lead["lead_id"]

    r = client.post(f"/api/v1/leads/{lead_id}/decision",
                    json={"action": "APPROVE_CONTACT", "note": "مؤهل ممتاز"})
    assert r.status_code == 200
    body = db.one("SELECT disposition, decided_by, disposition_note FROM leads"
                  " WHERE lead_id=?", (lead_id,))
    assert body["disposition"] == "APPROVE_CONTACT"
    assert body["decided_by"] == "dev-open"
    # APPROVE_CONTACT is terminal — the response says so, no send exists
    assert "لا يوجد أي إرسال تلقائي" in r.json()["note"]

    # human changes their mind later: allowed, both recorded in audit
    client.post(f"/api/v1/leads/{lead_id}/decision",
                json={"action": "SAVE_FOR_LATER"})
    audit = db.query("SELECT action FROM audit_logs ORDER BY id")
    actions = [a["action"] for a in audit]
    assert actions.count("lead.approve_contact") == 1
    assert "lead.save_for_later" in actions
    assert db.one("SELECT disposition FROM leads WHERE lead_id=?",
                  (lead_id,))["disposition"] == "SAVE_FOR_LATER"


def test_reject_decision(client, db):
    _run_research_job(db)
    lead_id = db.one("SELECT lead_id FROM leads")["lead_id"]
    resp = client.post(f"/api/v1/leads/{lead_id}/decision",
                       json={"action": "REJECT", "note": "خارج نطاقنا"})
    assert resp.status_code == 200
    assert db.one("SELECT disposition FROM leads WHERE lead_id=?",
                  (lead_id,))["disposition"] == "REJECT"


def test_invalid_decision_rejected(client, db):
    _run_research_job(db)
    lead_id = db.one("SELECT lead_id FROM leads")["lead_id"]
    resp = client.post(f"/api/v1/leads/{lead_id}/decision",
                       json={"action": "SEND_EMAIL"})
    assert resp.status_code == 422  # not a decision — and never will be


def test_review_board_lists_presentations(client, db):
    _run_research_job(db)
    resp = client.get("/api/v1/review/pending")
    assert resp.status_code == 200
    leads = resp.json()["leads"]
    assert len(leads) == 1
    assert leads[0]["fit"]["fit_score"] == 82
    assert leads[0]["lead"]["lead_id"] == "org-test:clinica-sa.com"


# --------------------------------------------------------- RESEARCH_MORE
def test_research_more_creates_child_job_with_context(client, db):
    job_id = _run_research_job(db)
    lead_id = db.one("SELECT lead_id FROM leads")["lead_id"]
    resp = client.post(f"/api/v1/leads/{lead_id}/decision",
                       json={"action": "RESEARCH_MORE", "note": "دور على الإيميل"})
    assert resp.status_code == 200
    child_job = resp.json()["child_job_id"]
    assert child_job
    ctx = ResearchJobManager(db).context(child_job)
    assert ctx["parent_job_id"] == job_id
    assert "clinica-sa.com" in ctx["objective"]
    # facts persist across jobs (subject-keyed): the child sees the parent's facts
    store = FactsStore(db)
    snap = store.snapshot("company", "clinica-sa.com")
    assert snap["fields"]["phone"]["value"] == "+966501111111"


# ---------------------------------------------------------- requalify
def test_requalify_from_facts_without_rediscovery(client, db):
    _run_research_job(db)
    lead_id = db.one("SELECT lead_id FROM leads")["lead_id"]
    searches_before = db.one("SELECT COUNT(*) AS n FROM usage_ledger")["n"]
    facts_before = db.one("SELECT COUNT(*) AS n FROM research_facts")["n"]

    from lead_engine.icp_store import ICPStore

    v2 = ICPStore(db).create_version("agentic", {"industry": "dental",
                                                 "cities": [{"name": "Jeddah"}]})
    ICPStore(db).activate(v2["icp_version_id"])
    resp = client.post(f"/api/v1/leads/{lead_id}/requalify", json={})
    assert resp.status_code == 200
    fit = resp.json()["presentation"]["fit"]
    # the ICP now targets Jeddah; the stored city fact says Riyadh -> hard fail
    assert fit["fit_score"] == 0
    assert fit["deterministic"] is True
    # NOTHING was re-discovered: same facts, zero new provider spend
    assert db.one("SELECT COUNT(*) AS n FROM research_facts")["n"] == facts_before
    assert db.one("SELECT COUNT(*) AS n FROM usage_ledger")["n"] == searches_before


# ------------------------------------------------- ICP API (user criteria)
def test_icp_api_create_activate_and_filter(db, client):
    """Stage 2 gate: the user defines what qualifies — versioned + active —
    and the agentic pipeline filters against IT."""
    r = client.post("/api/v1/icps", json={
        "slug": "agentic",
        "definition": {"industry": "dental",
                       "cities": [{"name": "Jeddah"}],
                       "criteria": {"min_branches": 3}},
    })
    assert r.status_code == 200
    icp = r.json()["icp"]
    assert icp["status"] == "active"
    lst = client.get("/api/v1/icps").json()
    assert lst["active"]["icp_version_id"] == icp["icp_version_id"]
    # activating a new version retires the old one
    r2 = client.post("/api/v1/icps", json={
        "slug": "agentic",
        "definition": {"industry": "dental", "cities": [{"name": "Riyadh"}]},
    })
    assert r2.status_code == 200
    versions = {v["version"]: v["status"] for v in
                client.get("/api/v1/icps").json()["versions"]}
    assert versions["v1"] == "retired" and versions["v2"] == "active"


def test_chat_define_icp_tool(db):
    """Chat-first criteria: 'عايز عيادات في جدة 3 فروع أكتر' becomes an
    ACTIVE ICP version via the define_icp tool."""
    from lead_engine.api.chat import execute_tool
    from lead_engine.cache import CacheLayer
    from lead_engine.config import load_cache_policy
    from lead_engine.router import Router

    router = Router(db, CacheLayer(db, load_cache_policy()), {})
    out = execute_tool("define_icp", {
        "industry": "dental", "cities": ["جدة"], "min_branches": 3,
        "notes": "نشاط تسويقي واضح",
    }, router, db)
    assert out["status"] == "ACTIVE"
    definition = out["definition"]
    assert definition["criteria"]["min_branches"] == 3
    # and start_research automatically binds the active ICP
    out2 = execute_tool("start_research", {"objective": "دور على عيادات"},
                        router, db)
    ctx = ResearchJobManager(db).context(out2["job_id"])
    assert ctx["icp_version_id"] == out["icp_version_id"]


def test_conflict_resolution_api(client, db):
    from lead_engine.truth import FactsStore, STATUS_VERIFIED
    store = FactsStore(db)
    f1 = store.record_fact("company", "org:clinic-c.com", "phone", "+966501111111",
                           source_url="https://c.com/1", provider="tavily")
    store.record_fact("company", "org:clinic-c.com", "phone", "+966502222222",
                      source_url="https://c.com/2", provider="brave")
    confs = client.get("/api/v1/conflicts").json()["conflicts"]
    assert len(confs) >= 1
    cid = confs[0]["conflict_id"]

    res = client.post(f"/api/v1/conflicts/{cid}/resolve",
                      json={"winner_fact_id": f1["fact_id"], "note": "verified"}).json()
    assert res["ok"] is True
    assert res["conflict"]["winner"] == f1["fact_id"]
    snap = store.snapshot("company", "org:clinic-c.com")
    assert snap["fields"]["phone"]["value"] == "+966501111111"
    assert snap["fields"]["phone"]["status"] == STATUS_VERIFIED
