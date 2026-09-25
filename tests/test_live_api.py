"""Live channel (SSE) — the dashboard's single real-time subscription.

Pinned behaviour:
  * the stream carries the same payload as `GET /api/status` (instant client),
  * an unscoped (no-org) client is refused instead of shown global totals,
  * the stream is bounded by `max_seconds`,
  * the request-scoped handle is released before streaming so a long-lived
    viewer never pins a pooled connection.
"""
import json

import pytest
from fastapi.testclient import TestClient

from lead_engine.api.app import app, get_db
from lead_engine.db import Database


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.delenv("LEAD_ENGINE_ORG_ID", raising=False)
    database = Database(tmp_path / "live.sqlite3")
    database.org_id = None
    return database


@pytest.fixture()
def client(db):
    def override():
        yield db

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_live_stream_emits_status_snapshot(client):
    with client.stream("GET", "/api/v1/live/stream?max_seconds=1") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        snap = _read_snapshot(resp)
    assert set(snap) >= {"providers", "jobs_by_state", "leads_by_stage",
                         "leads_total", "usage_totals"}
    assert isinstance(snap["jobs_by_state"], dict)


def test_live_stream_refuses_unscoped_tenant(client, db):
    """A client that cannot be scoped to an org gets an explicit error, never
    platform-wide totals."""
    db.org_id = "__no_org__"
    with client.stream("GET", "/api/v1/live/stream?max_seconds=1") as resp:
        body = "".join(resp.iter_text())
    assert "no_org" in body
    assert "snapshot" not in body


def test_live_snapshot_counts_are_org_scoped(client, db):
    db.org_id = "org-live"
    db.execute(
        "INSERT INTO jobs (job_id, state, organization_id, created_at, updated_at)"
        " VALUES (?,?,?,?,?)",
        ("job-live-1", "RUNNING", "org-live", "2026-01-01T00:00:00Z",
         "2026-01-01T00:00:00Z"),
    )
    with client.stream("GET", "/api/v1/live/stream?max_seconds=1") as resp:
        snap = _read_snapshot(resp)
    assert snap["jobs_by_state"].get("RUNNING") == 1


def test_live_usage_today_reflects_ledger(client, db):
    db.org_id = "org-live"
    db.execute(
        "INSERT INTO usage_ledger (ts, provider, task, units, organization_id)"
        " VALUES (?,?,?,?,?)",
        ("2026-01-01T00:00:00Z", "tavily", "search", 3, "org-live"),
    )
    with client.stream("GET", "/api/v1/live/stream?max_seconds=1") as resp:
        snap = _read_snapshot(resp)
    assert any(r["provider"] == "tavily" and r["calls"] == 1 for r in snap["usage_totals"])


def _read_snapshot(resp) -> dict:
    """Pull the first `snapshot` frame out of an SSE stream."""
    event = None
    for line in resp.iter_lines():
        if not line:
            continue
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and event == "snapshot":
            return json.loads(line.split(":", 1)[1].strip())
    raise AssertionError("no snapshot frame emitted")
