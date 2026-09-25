"""Statement-budget guards for the two dashboard-poll endpoints (TEST-02).

`/api/status` is polled every few seconds and `/api/analytics` renders the
Overview chart; both once multiplied per-provider/per-day reads. The measured
floor (scratch/measure_status_statements.py, 2026-09-25) is 8 and 3
statements respectively; the budgets add slack for honest evolution but any
return to per-row queries fails here.
"""
import os

os.environ.setdefault("LEAD_ENGINE_DEV_OPEN", "1")
for _key in ("SUPABASE_DB_URL", "DATABASE_URL", "LEAD_ENGINE_ADMIN_PASSWORD",
             "LEAD_ENGINE_ORG_ID"):
    os.environ[_key] = ""

import pytest
from fastapi.testclient import TestClient

from tests.test_bootstrap_idempotence import CountingDb
from lead_engine.bootstrap import reset as reset_bootstrap
from lead_engine.db import Database
from lead_engine.agent_registry import ensure_seeded

import lead_engine.api.app as appmod

STATUS_BUDGET = 8 + 2    # measured 8: grouped ledger, providers, jobs, leads,
ANALYTICS_BUDGET = 3 + 2  # approvals, last job, cache, usage-by-provider


@pytest.fixture()
def counted_client(tmp_path, request, monkeypatch):
    reset_bootstrap()
    store = tmp_path / "budget.sqlite3"
    Database(store)  # create file + schema
    ensure_seeded(Database(store))
    holder = {}

    def fake_open_db(org_id=None):
        cdb = CountingDb(Database(store))
        holder["db"] = cdb
        return cdb

    monkeypatch.setattr(appmod, "open_db", fake_open_db)
    request.addfinalizer(appmod._status_cache.clear)
    appmod._status_cache.clear()
    with TestClient(appmod.app) as client:
        yield client, holder


def test_status_stays_within_statement_budget(counted_client):
    client, holder = counted_client
    res = client.get("/api/status")
    assert res.status_code == 200, res.text
    assert len(res.json()["providers"]) > 0, "payload must not be quietly emptied"
    assert holder["db"].count <= STATUS_BUDGET, (
        f"/api/status issued {holder['db'].count} statements "
        f"(budget {STATUS_BUDGET}): {holder['db'].sql}")


def test_analytics_stays_within_statement_budget(counted_client):
    client, holder = counted_client
    res = client.get("/api/analytics")
    assert res.status_code == 200, res.text
    assert holder["db"].count <= ANALYTICS_BUDGET, (
        f"/api/analytics issued {holder['db'].count} statements "
        f"(budget {ANALYTICS_BUDGET}): {holder['db'].sql}")
