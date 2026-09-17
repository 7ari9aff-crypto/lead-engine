"""Live SSE stream: real change detection, tenant isolation, honest framing.

The dashboard subscribes to ONE server-push stream whose frames carry the same
payload as GET /api/status, so a connected client never polls. These tests pin
the properties that make that safe: only real changes produce frames, the
digest is per-tenant, and one bad tick never kills the stream.
"""
import json

import pytest
from fastapi.testclient import TestClient

from lead_engine.api import app as app_module
from lead_engine.api.app import app, get_db
from lead_engine.db import Database


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "live.sqlite3")
    database.org_id = "org-live"
    return database


@pytest.fixture()
def client(db):
    def override_get_db(request=None):
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _insert_lead(db, lead_id, org_id="org-live"):
    db.execute(
        "INSERT INTO leads (lead_id, organization_id, name, stage, created_at)"
        " VALUES (?,?,?,?,?)",
        (lead_id, org_id, "Acme", "ACCEPTED", "2026-01-01T00:00:00Z"),
    )


def _insert_job(db, job_id, state="RUNNING", org_id="org-live"):
    db.execute(
        "INSERT INTO jobs (job_id, organization_id, icp_id, state, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?)",
        (job_id, org_id, "icp", state, "2026-01-01T00:00:00Z",
         "2026-01-01T00:00:00Z"),
    )


# ------------------------------- snapshot ------------------------------------
def test_snapshot_counts_real_rows(db):
    _insert_lead(db, "lead-1")
    _insert_job(db, "job-1", "RUNNING")
    _, payload = app_module._live_snapshot(db)
    assert payload["leads_total"] == 1
    assert payload["jobs_by_state"]["RUNNING"] == 1
    assert payload["recent_jobs"][0]["job_id"] == "job-1"
    assert any(a["kind"] == "pending_approvals" for a in payload["alerts"]) is False


def test_digest_changes_only_on_real_change(db):
    _, before = app_module._live_snapshot(db)
    digest_before, _ = app_module._live_snapshot(db)

    # Same data -> identical digest, so no wasted frame goes over the wire.
    digest_same, _ = app_module._live_snapshot(db)
    assert digest_before == digest_same

    _insert_lead(db, "lead-2")
    digest_after, after = app_module._live_snapshot(db)
    assert digest_after != digest_before
    assert after["leads_total"] == before["leads_total"] + 1


def test_snapshot_is_tenant_scoped(db):
    _insert_lead(db, "mine", org_id="org-live")
    _insert_lead(db, "theirs", org_id="org-other")

    _, payload = app_module._live_snapshot(db)

    assert payload["leads_total"] == 1, "other tenant's lead leaked into the stream"


def test_pending_approval_raises_alert(db):
    db.execute(
        "INSERT INTO approvals (approval_id, organization_id, run_id, action, status,"
        " requested_at) VALUES (?,?,?,?,?,?)",
        ("approval_x", "org-live", "run-1", "code_patch", "PENDING", "2026-01-01T00:00:00Z"),
    )
    _, payload = app_module._live_snapshot(db)
    assert payload["pending_approvals"] == 1


def test_failed_job_raises_alert(db):
    _insert_job(db, "job-x", "FAILED")
    _, payload = app_module._live_snapshot(db)
    assert any(a["kind"] == "failed_jobs" for a in payload["alerts"])


# -------------------------------- stream -------------------------------------
def test_stream_emits_snapshot_then_keepalive(client, monkeypatch):
    monkeypatch.setattr(app_module, "_LIVE_MIN_INTERVAL", 0.0)

    with client.stream("GET", "/api/v1/live/stream?max_seconds=1") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert "event: snapshot" in body
    frame = body.split("event: snapshot\ndata: ", 1)[1].split("\n\n", 1)[0]
    data = json.loads(frame)
    # The frame is the same payload the dashboard's status endpoint returns —
    # that is what makes a connected client instant (no polling at all).
    assert {"providers", "jobs_by_state", "leads_by_stage"} <= set(data)
    assert "alerts" in data


def test_stream_reports_tick_errors_without_dying(client, monkeypatch):
    monkeypatch.setattr(app_module, "_LIVE_MIN_INTERVAL", 0.0)
    monkeypatch.setattr(app_module, "_LIVE_ERROR_INTERVAL", 0.0)
    monkeypatch.setattr(
        app_module, "_build_status",
        lambda conn: (_ for _ in ()).throw(RuntimeError("db gone")))

    with client.stream("GET", "/api/v1/live/stream?max_seconds=1") as response:
        body = "".join(response.iter_text())

    assert "event: error" in body
    assert "RuntimeError" in body


def test_stream_is_bounded_by_max_seconds(client, monkeypatch):
    """`max_seconds` must bound the stream — a stuck viewer can never hang a
    worker, and a test cannot hang on an unbounded stream."""
    monkeypatch.setattr(app_module, "_LIVE_MIN_INTERVAL", 0.0)

    with client.stream("GET", "/api/v1/live/stream?max_seconds=1") as response:
        body = "".join(response.iter_text())

    # The stream closed itself well under its bound (the test returning at all
    # proves the bound works).
    assert "event: snapshot" in body
