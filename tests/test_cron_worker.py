"""The worker-tick HTTP surface: GET /api/cron/worker.

Lives on the FastAPI app, not on a Vercel filesystem function, because the
FastAPI preset rewrites every path to `api/index.py` — a sibling
`api/cron/worker.py` was never reachable in production, and its 401 was the
app's auth middleware answering, not the endpoint's own fail-closed check.
The same route therefore serves Vercel, Docker and the local worker loop.

Auth is a dedicated bearer secret (CRON_SECRET), verified inside the handler
and exempted from the session middleware exactly like the Stripe webhook: the
caller is a scheduler with no session, cookie or JWT. Absent CRON_SECRET means
"reject everything", so a misconfigured platform cannot drive the queue.

conftest's env leaves the app in `open` mode (LEAD_ENGINE_DEV_OPEN=1 from
.env), so `test_closed_mode_still_ticks` forces the gate shut to prove the
middleware really exempts this path — without the exemption the answer would
be the middleware's `{"detail": ...}` 401, never the handler's own decision.
"""
import json

import pytest
from fastapi.testclient import TestClient

from lead_engine.db import Database

SECRET = "cron-secret-1"


@pytest.fixture
def cron_client(monkeypatch, tmp_path):
    """A TestClient whose DB is a temp SQLite file and whose tick is fakeable.

    The handler resolves `open_db` lazily from `lead_engine.db`, so that is the
    patch point — patching the app module's binding would silently leave the
    test pointed at the real database.
    """
    import lead_engine.api.app as appmod

    store = tmp_path / "cron.sqlite3"
    monkeypatch.setattr("lead_engine.db.open_db", lambda *a, **k: Database(store))
    monkeypatch.delenv("LEAD_ENGINE_MCP_TOKEN", raising=False)
    return TestClient(appmod.app), monkeypatch


def test_missing_secret_rejects(cron_client):
    client, mp = cron_client
    mp.setenv("CRON_SECRET", "")
    r = client.get("/api/cron/worker")
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}  # the endpoint's own shape


def test_wrong_token_rejects(cron_client):
    client, mp = cron_client
    mp.setenv("CRON_SECRET", SECRET)
    r = client.get("/api/cron/worker", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}


def test_bearer_is_the_only_accepted_form(cron_client):
    """A raw token without the scheme, or the wrong scheme, must not pass."""
    client, mp = cron_client
    mp.setenv("CRON_SECRET", SECRET)
    for header in ({"Authorization": SECRET}, {"Authorization": f"Basic {SECRET}"}):
        assert client.get("/api/cron/worker", headers=header).status_code == 401


def test_closed_mode_still_ticks(cron_client):
    """The production defect this file exists for.

    With no auth backend configured the session middleware 401s every
    protected path (`mode == "closed"`). `/api/cron/worker` must be exempt at
    the middleware and answer from its own bearer check — otherwise the
    scheduler can never reach the queue, which is exactly what happened in
    production with `api/cron/worker.py`: the 401 in the logs was the
    middleware, and the tick was unreachable.
    """
    client, mp = cron_client
    mp.delenv("LEAD_ENGINE_DEV_OPEN", raising=False)
    mp.delenv("SUPABASE_URL", raising=False)
    mp.delenv("LEAD_ENGINE_ADMIN_PASSWORD", raising=False)
    from lead_engine.api import auth_jwt

    assert auth_jwt.auth_mode() == "closed"  # the gate is genuinely shut

    mp.setenv("CRON_SECRET", SECRET)
    mp.setattr("lead_engine.worker.run_worker_tick",
               lambda db, worker_id, settings=None, lease_seconds=600: {
                   "worker_id": worker_id, "reclaimed": 0, "stale_runs_reaped": 0,
                   "leased": False, "job_id": None, "state": None,
                   "retention_erased": 0, "error": None})
    ok = client.get("/api/cron/worker",
                    headers={"Authorization": f"Bearer {SECRET}"})
    assert ok.status_code == 200
    # Denied without the bearer, and it is the HANDLER that says so.
    denied = client.get("/api/cron/worker")
    assert denied.status_code == 401
    assert denied.json() == {"error": "unauthorized"}


def test_valid_cron_runs_one_tick(cron_client):
    client, mp = cron_client
    mp.setenv("CRON_SECRET", SECRET)
    mp.setenv("VERCEL_REGION", "iad1")
    tick_args = {}

    def fake_tick(db, worker_id, settings=None, lease_seconds=600):
        tick_args["worker_id"] = worker_id
        return {"worker_id": worker_id, "reclaimed": 1, "stale_runs_reaped": 0,
                "leased": False, "job_id": None, "state": None,
                "retention_erased": 0, "error": None}

    mp.setattr("lead_engine.worker.run_worker_tick", fake_tick)
    r = client.get("/api/cron/worker", headers={"Authorization": f"Bearer {SECRET}"})
    assert r.status_code == 200
    body = r.json()
    assert body["reclaimed"] == 1
    assert body["worker_id"] == "cron-iad1"
    assert tick_args["worker_id"] == "cron-iad1"


def test_tick_failure_returns_500_with_reason(cron_client):
    client, mp = cron_client
    mp.setenv("CRON_SECRET", SECRET)

    def fake_tick(db, worker_id, settings=None, lease_seconds=600):
        raise RuntimeError("db down")

    mp.setattr("lead_engine.worker.run_worker_tick", fake_tick)
    r = client.get("/api/cron/worker", headers={"Authorization": f"Bearer {SECRET}"})
    assert r.status_code == 500
    assert "db down" in json.loads(r.text)["error"]
