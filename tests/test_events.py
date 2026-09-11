"""Event backbone + provisioning: outbox idempotency, signed webhooks with
DLQ, notifications, provisioning state machine (SQLite-portable paths)."""
import json

import pytest
import requests

from lead_engine import events, provisioning
from lead_engine.db import Database


@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / "events.sqlite3")
    db.execute("CREATE TABLE IF NOT EXISTS organizations (id TEXT PRIMARY KEY, slug TEXT)")
    db.execute("INSERT INTO organizations (id, slug) VALUES ('org-1', 'lead-engine')")
    db.execute("""CREATE TABLE IF NOT EXISTS webhooks (
        id TEXT PRIMARY KEY, organization_id TEXT, url TEXT,
        secret_enc TEXT, events TEXT, status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT '', updated_at TEXT DEFAULT '')""")
    db.execute("""CREATE TABLE IF NOT EXISTS webhook_deliveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, webhook_id TEXT, event_id TEXT,
        url TEXT, attempt INT, status_code INT, success INT, error TEXT,
        created_at TEXT DEFAULT '')""")
    db.execute("""CREATE TABLE IF NOT EXISTS outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE,
        organization_id TEXT, aggregate_type TEXT, aggregate_id TEXT,
        event_type TEXT, event_version INT DEFAULT 1, payload TEXT,
        status TEXT DEFAULT 'pending', attempts INT DEFAULT 0,
        last_error TEXT, created_at TEXT DEFAULT '', published_at TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS event_consumptions (
        event_id TEXT, consumer TEXT, processed_at TEXT DEFAULT '',
        PRIMARY KEY (event_id, consumer))""")
    db.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, organization_id TEXT, kind TEXT,
        title TEXT, body TEXT, read INT DEFAULT 0, created_at TEXT DEFAULT '')""")
    db.execute("""CREATE TABLE IF NOT EXISTS tenant_provisioning (
        org_id TEXT PRIMARY KEY, state TEXT, isolation_level TEXT,
        steps TEXT DEFAULT '[]', error TEXT, requested_by TEXT,
        created_at TEXT DEFAULT '', updated_at TEXT DEFAULT '')""")
    yield db
    db.conn.close()


def _emit_job_completed(db, event_id="evt-1"):
    return events.emit(db, "org-1", "job.completed", "job", "job-1",
                       {"leads": 12}, event_id=event_id)


def test_emit_is_idempotent(db):
    e1 = _emit_job_completed(db)
    e2 = _emit_job_completed(db)
    assert e1 == e2
    assert len(db.query("SELECT * FROM outbox")) == 1


def test_dispatch_marks_dispatched_and_notifies(db):
    _emit_job_completed(db)
    counts = events.dispatch_pending(db)
    assert counts["dispatched"] == 1
    row = db.one("SELECT status FROM outbox WHERE event_id='evt-1'")
    assert row["status"] == "dispatched"
    notes = db.query("SELECT kind, title FROM notifications")
    assert len(notes) == 1 and notes[0]["kind"] == "job.completed"
    # idempotent: re-dispatch does nothing
    counts = events.dispatch_pending(db)
    assert counts["dispatched"] == 0
    assert len(db.query("SELECT * FROM notifications")) == 1


def test_signed_webhook_delivery(db, monkeypatch):
    import base64
    from lead_engine.secrets import encrypt_secret
    import os

    monkeypatch.setenv("LEAD_ENGINE_ENCRYPTION_KEY",
                       base64.urlsafe_b64encode(os.urandom(32)).decode())
    secret = "whsec_test"
    calls = []

    class FakeResp:
        status_code = 200

    def fake_post(url, data=None, timeout=None, headers=None):
        calls.append({"url": url, "body": json.loads(data), "headers": headers})
        return FakeResp()

    monkeypatch.setattr(events.requests, "post", fake_post)
    db.execute("INSERT INTO webhooks (id, organization_id, url, secret_enc, events)"
               " VALUES ('wh-1', 'org-1', 'https://hooks.example/x', ?, '*')",
               (encrypt_secret(secret),))
    _emit_job_completed(db)
    counts = events.dispatch_pending(db)
    assert counts["dispatched"] == 1
    assert len(calls) == 1
    sig = calls[0]["headers"]["X-LeadEngine-Signature"]
    assert sig.startswith("v1=")
    # receiver-side verification passes with the same secret
    ts = calls[0]["headers"]["X-LeadEngine-Timestamp"]
    body = json.dumps(calls[0]["body"], ensure_ascii=False)
    assert events.verify_webhook_signature(secret, ts, body, sig)
    # and the delivery was logged as success
    d = db.one("SELECT success FROM webhook_deliveries WHERE event_id='evt-1'")
    assert d["success"] in (1, True)


def test_webhook_failure_goes_to_dead_letter(db, monkeypatch):
    import base64
    from lead_engine.secrets import encrypt_secret
    import os

    monkeypatch.setenv("LEAD_ENGINE_ENCRYPTION_KEY",
                       base64.urlsafe_b64encode(os.urandom(32)).decode())

    class FailResp:
        status_code = 500

    monkeypatch.setattr(events.requests, "post", lambda *a, **k: FailResp())
    db.execute("INSERT INTO webhooks (id, organization_id, url, secret_enc, events)"
               " VALUES ('wh-1', 'org-1', 'https://hooks.example/x', ?, '*')",
               (encrypt_secret("whsec_x"),))
    _emit_job_completed(db)

    for _ in range(events.MAX_ATTEMPTS):
        events.dispatch_pending(db)
    row = db.one("SELECT status, attempts FROM outbox WHERE event_id='evt-1'")
    assert row["status"] == "dead"  # DLQ semantics
    deliveries = db.query("SELECT attempt FROM webhook_deliveries ORDER BY id")
    assert len(deliveries) >= 3  # retried inside each dispatch round


def test_notification_failure_does_not_block_dispatch(db, monkeypatch):
    # a broken consumer must not deadlock the outbox: webhooks ran, error raises
    _emit_job_completed(db)
    monkeypatch.setattr(events, "_consume_notifications",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    counts = events.dispatch_pending(db)
    assert counts["retried"] == 1
    row = db.one("SELECT attempts FROM outbox WHERE event_id='evt-1'")
    assert row["attempts"] == 1


def test_provisioning_state_machine(db):
    result = provisioning.provision(db, "org-1")
    assert result["state"] == provisioning.ACTIVE
    row = provisioning.status(db, "org-1")
    assert row["state"] == "ACTIVE"
    steps = json.loads(row["steps"])
    assert steps[-1]["step"] == "activate"
    # idempotent guard: provisioning an ACTIVE org with same fn is a no-op state
    result2 = provisioning.provision(db, "org-1")
    assert result2["state"] == provisioning.ACTIVE


def test_provisioning_failure_marks_failed(db):
    def broken_handler():
        raise RuntimeError("cluster unavailable")

    result = provisioning.provision(db, "org-1", isolation_level="dedicated",
                                    step_handlers={"dedicated": broken_handler})
    assert result["state"] == provisioning.FAILED
    row = provisioning.status(db, "org-1")
    assert "cluster unavailable" in row["error"]
    # retry path: FAILED -> PROVISIONING is legal
    import json as _json
    db.execute("UPDATE tenant_provisioning SET isolation_level='pooled' WHERE org_id='org-1'")
    result = provisioning.provision(db, "org-1")
    assert result["state"] == provisioning.ACTIVE
