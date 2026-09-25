"""P0 E2E — live stack: POST /benchmark/run -> job row -> materialized leads
-> GET /api/status shows REAL counts. Mirrors tests/test_e2e_research.py:
real FastAPI app (TestClient), temp SQLite DB, no network, no quota.

Proves the classic benchmark path end-to-end instead of only the research
path: scripted router returns search/LLM payloads, the orchestrator writes
jobs + leads + usage_ledger, and the dashboard status endpoint reflects them.
"""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from lead_engine.api import app as app_module
from lead_engine.api.app import app
from lead_engine.db import Database
from tests.conftest import seed_control_plane


class _KeepOpen:
    """Forward to the real sqlite3 connection but ignore ``close()``.

    ``run_benchmark`` owns the connection it opens and closes it before
    returning; the test still needs to query the same database afterwards, so
    the close is swallowed. Every other attribute (``execute``, ``commit``, …)
    is forwarded untouched, keeping the exercised SQL identical to production.
    """

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        """Keep the connection alive for assertions after the run."""


@pytest.fixture()
def db(tmp_path, monkeypatch):
    database = Database(tmp_path / "e2e_stack.sqlite3")
    database.org_id = "org-e2e-stack"
    # /benchmark/run opens an agent run, which needs the seeded control plane.
    seed_control_plane(database)
    database.conn = _KeepOpen(database.conn)
    # The runner opens its own handle (production: DSN-backed). Point that
    # factory at the temp database so the whole path runs against real SQL
    # without touching the developer's lead_engine.sqlite3.
    monkeypatch.setattr("lead_engine.benchmark.run.open_db", lambda *a, **k: database)
    # Report artifacts are a filesystem side effect; the E2E asserts data, not files.
    monkeypatch.setattr("lead_engine.benchmark.run.write_outputs", lambda *a, **k: {})
    return database


@pytest.fixture()
def client(db):
    def _get_db(request=None):
        yield db

    app.dependency_overrides[app_module.get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.pop(app_module.get_db, None)


_SEARCH = {
    "results": [
        {"title": "Dental Clinic Alpha — Jeddah", "url": "https://alpha-clinic.test",
         "snippet": "dental clinic in Jeddah, call +966 12 345 6789 or email info@alpha-clinic.test"},
        {"title": "Dental Clinic Beta — Riyadh", "url": "https://beta-clinic.test",
         "snippet": "dental clinic in Riyadh — dentist, book@beta-clinic.test"},
    ],
    "units": 1,
}
# The qualifier parses the LLM text as JSON: {"score": 0..100, "tier": ...}.
_LLM = {"text": json.dumps({"score": 85, "tier": "A", "reasons": ["active ads"]}), "units": 1}


def _fake_route(self, task, payload, job_id=None, **kwargs):
    """Scripted provider layer: no network, deterministic payloads per task."""
    if task in ("web_search", "apollo_search", "company_search", "search"):
        return copy.deepcopy(_SEARCH), {"provider": "tavily-test", "cached": False}
    if task in ("email_verify", "email_verification", "email_find"):
        # VerificationPipeline._via_provider reads result["status"] directly.
        return {"status": "DELIVERABLE", "confidence": 0.9, "units": 0,
                "provider": "hunter-test", "details": {"reason": "scripted"}}, \
               {"provider": "hunter-test", "cached": False}
    return copy.deepcopy(_LLM), {"provider": "gemini-test", "cached": False}


@pytest.fixture()
def scripted_router(monkeypatch):
    monkeypatch.setattr(
        "lead_engine.pipeline.orchestrator.Router.route", _fake_route, raising=False)


def test_benchmark_run_materializes_job_and_leads(client, db, scripted_router):
    """POST /benchmark/run -> job row + materialized leads -> /api/status real."""
    res = client.post("/benchmark/run", json={
        "icp": "v0_saudi_dental",
        # Keep discovery tiny: 1 query x 2 scripted results so the E2E stays fast.
        "overrides": {"v0_limits": {"search_results_per_query": 2,
                                    "max_search_queries": 1,
                                    "enrichment_budget_credits": 0,
                                    "enrichment_max_people": 0}},
    })
    assert res.status_code == 200, res.text
    body = res.json()
    job_id = body["job_id"]
    assert job_id

    job = db.one("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
    assert job is not None

    leads = db.query("SELECT * FROM leads WHERE job_id = ?", (job_id,))
    assert len(leads) >= 1, f"expected materialized leads, job state={job.get('state')}"

    status = client.get("/api/status").json()
    assert (status.get("jobs_by_state") or {}), "status must show real job counts"
    total_jobs = sum((status.get("jobs_by_state") or {}).values())
    assert total_jobs >= 1

    # Report endpoint serves the same job (contract both dashboard + n8n rely on).
    rep = client.get(f"/api/v1/report/{job_id}")
    assert rep.status_code == 200, rep.text
    assert rep.json().get("job_id") == job_id
