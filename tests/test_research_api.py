"""R2/R3 API tests: research jobs over HTTP (isolated temp DB, no network)."""
import pytest
from fastapi.testclient import TestClient

from lead_engine.api import research_api
from lead_engine.api.app import app
from lead_engine.db import Database
from lead_engine.research import ResearchJobManager


@pytest.fixture()
def db(tmp_path, monkeypatch):
    database = Database(tmp_path / "research_api.sqlite3")
    database.org_id = "org-test"
    return database


@pytest.fixture()
def client(db, monkeypatch):
    # NOTE: never `delenv` these — config.load_env() re-hydrates keys from the
    # local .env whenever they are ABSENT. conftest sets them to "" (load_env
    # only fills missing keys), which keeps auth dev-open and providers off.

    def override_get_db(request=None):
        yield db

    app.dependency_overrides[research_api.get_db] = override_get_db
    # background runs happen inline against the SAME temp db (never the dev db)
    def fake_run(job_id):
        from lead_engine.config import load_settings
        from lead_engine.research.orchestrator import ResearchOrchestrator

        ResearchOrchestrator(db, load_settings(), job_id).run()

    monkeypatch.setattr(research_api, "_run_research", fake_run)
    yield TestClient(app)
    app.dependency_overrides.pop(research_api.get_db, None)


def test_create_then_no_capacity_pauses_honestly(client, db):
    """With no provider keys in the test env the orchestrator pauses with
    NO_CAPACITY — the honest resource state, never a fake success."""
    resp = client.post("/api/v1/research",
                       json={"objective": "دور على عيادات في الرياض"})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    progress = client.get(f"/api/v1/research/{job_id}").json()
    assert progress["state"] == "PAUSED"
    assert "NO_CAPACITY" in (progress["pause_reason"] or "")
    assert progress["objective"] == "دور على عيادات في الرياض"


def test_create_requires_objective(client):
    assert client.post("/api/v1/research", json={"objective": ""}).status_code == 422


def test_progress_unknown_job_is_404(client):
    assert client.get("/api/v1/research/job-nope").status_code == 404


def test_cross_tenant_progress_is_404(db, client):
    manager = ResearchJobManager(db)
    job_id = manager.create("private objective")
    db.org_id = "other-org"
    assert client.get(f"/api/v1/research/{job_id}").status_code == 404


def test_cancel_flow(client, db):
    job_id = ResearchJobManager(db).create("objective")
    resp = client.post(f"/api/v1/research/{job_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["state"] == "CANCELLED"
    assert client.post(f"/api/v1/research/{job_id}/cancel").status_code == 409
    assert client.post(f"/api/v1/research/{job_id}/resume").status_code == 409


def test_answer_resumes_waiting_for_user(client, db):
    manager = ResearchJobManager(db)
    job_id = manager.create("objective")
    manager.jobs.transition(job_id, "RUNNING")
    manager.waiting_for_user(job_id, "أي مدينة؟")
    resp = client.post(f"/api/v1/research/{job_id}/answer", json={"answer": "جدة"})
    assert resp.status_code == 200
    # the background runner then pauses honestly (no providers in tests) —
    # which proves the resume actually reached the orchestrator
    assert manager.jobs.current(job_id) == "PAUSED"
    events = client.get(f"/api/v1/research/{job_id}/events").json()["events"]
    assert any("user answered: جدة" in (e["reason"] or "") for e in events)


def test_answer_rejects_non_waiting_job(client, db):
    job_id = ResearchJobManager(db).create("objective")
    assert client.post(f"/api/v1/research/{job_id}/answer",
                       json={"answer": "x"}).status_code == 409


def test_resume_from_ready_for_review_is_research_more(client, db):
    manager = ResearchJobManager(db)
    job_id = manager.create("objective")
    manager.jobs.transition(job_id, "RUNNING")
    manager.ready_for_review(job_id, "OBJECTIVE_SATISFIED")
    resp = client.post(f"/api/v1/research/{job_id}/resume")
    assert resp.status_code == 200
    # background runner pauses honestly (no providers) — proves the job left
    # READY_FOR_REVIEW and re-entered the loop (RESEARCH_MORE semantics)
    assert manager.jobs.current(job_id) == "PAUSED"
    events = client.get(f"/api/v1/research/{job_id}/events").json()["events"]
    assert any("RESEARCH_MORE" in (e["reason"] or "") for e in events)


def test_chat_start_research_tool_creates_job(db, monkeypatch):
    """The chat 'start_research' tool creates a persistent research job —
    the chat-first entry from directive §29."""
    from lead_engine.api.chat import execute_tool
    from lead_engine.cache import CacheLayer
    from lead_engine.config import load_cache_policy
    from lead_engine.router import Router

    class NullRouter(Router):
        def route(self, *a, **k):
            from lead_engine.router import NoProviderAvailable

            raise NoProviderAvailable("reasoning", tried=["none"])

    router = NullRouter(db, CacheLayer(db, load_cache_policy()), {})
    out = execute_tool("start_research", {"objective": "دور على شركات SaaS في السعودية"},
                       router, db)
    assert out["state"] == "QUEUED"
    assert out["job_id"].startswith("job-")
    manager = ResearchJobManager(db)
    assert manager.is_research(out["job_id"])
    assert "SaaS" in manager.context(out["job_id"])["objective"]
