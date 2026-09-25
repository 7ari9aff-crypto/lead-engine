"""PII retention sweep + erasure path (plan W4c, register DATA-03).

`legal_gate` computes a per-lead retention_days and the pipeline stores it in
the lead's `raw` JSON under "pipeline" (there is no dedicated column — measured
against db.py LEAD_COLUMNS, 2026-09-25). Nothing ever enforces it: leads keep
email/phone/decision-maker PII forever. This module adds the enforcement.

Design notes fixed by measurement, not preference:
  * No schema change: retention_days rides in raw->pipeline (a dedicated column
    would require a production migration + insert-column sync on both backends
    before any deploy — rejected as sequencing risk for this wave).
  * Erasure covers `raw` too: insert_lead serialises every non-column key into
    raw JSON, so NULLing the PII columns alone would leave the contacts inside
    raw — fake erasure.
  * The marker lives in `legal_decision` ('retention-erased'), NOT `disposition`
    (documented human-only: APPROVE_CONTACT | REJECT | RESEARCH_MORE |
    SAVE_FOR_LATER). Aggregates (stage, score, domain, name, sources) survive.
"""
import json
import os

os.environ.setdefault("LEAD_ENGINE_DEV_OPEN", "1")
for _key in ("SUPABASE_DB_URL", "DATABASE_URL", "LEAD_ENGINE_ADMIN_PASSWORD",
             "LEAD_ENGINE_ORG_ID"):
    os.environ[_key] = ""

from datetime import datetime, timedelta, timezone

import pytest

from lead_engine.db import Database
from lead_engine.privacy import erase_lead, retain_expired


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_lead(db, lead_id: str, *, created: datetime, retention_days=365,
               fresh=False):
    lead = {
        "lead_id": lead_id, "name": "Acme", "domain": "acme.com",
        "email": "a@acme.com", "phone": "+201000000000",
        "decision_maker": "Ali", "decision_maker_title": "CTO",
        "linkedin": "http://li.com/ali", "social": "{}",
        "email_status": "valid", "email_confidence": 0.9,
        "stage": "ACCEPTED", "qualification_score": 0.8, "score": 0.8,
        "created_at": _iso(created), "raw": json.dumps({"note": "provider payload"}),
    }
    if not fresh:
        lead["retention_days"] = retention_days
    db.insert_lead(lead)


@pytest.fixture()
def db(tmp_path):
    return Database(tmp_path / "privacy.sqlite3")


def test_retention_sweep_anonymizes_expired_leads(db):
    old = datetime.now(timezone.utc) - timedelta(days=400)
    _make_lead(db, "lead-1", created=old, retention_days=365)

    assert retain_expired(db) == 1

    row = db.one("SELECT * FROM leads WHERE lead_id LIKE '%lead-1'")
    for col in ("email", "phone", "decision_maker", "decision_maker_title",
                "linkedin", "social"):
        assert row[col] is None, f"{col} survived the sweep"
    assert row["stage"] == "ACCEPTED", "aggregates must survive"
    assert row["name"] == "Acme", "company identity is not personal PII"
    assert row["legal_decision"] == "retention-erased"
    assert "retention" in (row["disposition_note"] or "")
    raw = json.loads(row["raw"])
    assert "a@acme.com" not in row["raw"], "raw must be redacted, not kept"
    assert raw.get("retention") == "erased"


def test_retention_sweep_spares_live_leads(db):
    now = datetime.now(timezone.utc)
    _make_lead(db, "lead-live", created=now, retention_days=365)

    assert retain_expired(db) == 0

    row = db.one("SELECT email FROM leads WHERE lead_id LIKE '%lead-live'")
    assert row["email"] == "a@acme.com"


def test_retention_sweep_is_idempotent(db):
    old = datetime.now(timezone.utc) - timedelta(days=800)
    _make_lead(db, "lead-2", created=old, retention_days=365)

    assert retain_expired(db) == 1
    assert retain_expired(db) == 0, "already-erased rows must not be re-touched"


def test_retention_falls_back_to_policy_default(db):
    """A lead whose raw carries no pipeline.retention_days (older writer) uses
    legal_gate's default horizon of 30 days."""
    old = datetime.now(timezone.utc) - timedelta(days=31)
    _make_lead(db, "lead-3", created=old, fresh=True)

    assert retain_expired(db) == 1
    row = db.one("SELECT email FROM leads WHERE lead_id LIKE '%lead-3'")
    assert row["email"] is None


def test_erase_lead_erases_now_and_audits(db):
    now = datetime.now(timezone.utc)
    _make_lead(db, "lead-4", created=now, retention_days=365)

    assert erase_lead(db, db.one("SELECT lead_id FROM leads")["lead_id"],
                      "owner@example.com") is True

    row = db.one("SELECT * FROM leads")
    assert row["email"] is None and row["decision_maker"] is None
    assert row["legal_decision"] == "retention-erased"
    assert "erased-by-request" in (row["disposition_note"] or "")
    audit = db.one("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 1")
    assert audit["action"] == "privacy.erase"
    assert audit["actor"] == "owner@example.com"


def test_erase_lead_unknown_lead_returns_false(db):
    assert erase_lead(db, "does-not-exist", "owner@example.com") is False


# ---- worker tick integration ----


def test_tick_reports_retention_erased(tmp_path, monkeypatch):
    import lead_engine.privacy as privacy
    from lead_engine.worker import run_worker_tick

    db = Database(tmp_path / "tick.sqlite3")
    monkeypatch.setattr(privacy, "retain_expired", lambda d: 3)
    result = run_worker_tick(db, "w-ret", settings={})
    assert result["retention_erased"] == 3


def test_tick_survives_sweep_failure(tmp_path, monkeypatch):
    import lead_engine.privacy as privacy
    from lead_engine.worker import run_worker_tick

    db = Database(tmp_path / "tick2.sqlite3")

    def boom(_db):
        raise RuntimeError("sweep down")

    monkeypatch.setattr(privacy, "retain_expired", boom)
    result = run_worker_tick(db, "w-ret2", settings={})
    assert result["retention_erased"] == -1
    assert result["error"] is None or result["error"] is None  # tick itself must not fail


# ---- erasure endpoint (plan Task 8) ----


def _erase_client(tmp_path, monkeypatch):
    import lead_engine.api.app as appmod
    from fastapi.testclient import TestClient
    from lead_engine.bootstrap import reset as reset_bootstrap

    reset_bootstrap()
    dbfile = tmp_path / "erase.sqlite3"
    store = Database(dbfile)
    _make_lead(store, "lead-erase-me",
               created=datetime.now(timezone.utc), retention_days=365)

    def fake_open_db(org_id=None):
        d = Database(dbfile)
        d.org_id = "org-t"
        return d

    monkeypatch.setattr(appmod, "open_db", fake_open_db)
    return TestClient(appmod.app), dbfile


def test_erase_endpoint_erases_and_audits(tmp_path, monkeypatch):
    client, dbfile = _erase_client(tmp_path, monkeypatch)

    r = client.post("/api/privacy/erase", json={"lead_id": "lead-erase-me"})

    assert r.status_code == 200, r.text
    assert r.json() == {"lead_id": "lead-erase-me", "erased": True}
    row = Database(dbfile).one("SELECT email, legal_decision FROM leads"
                               " WHERE lead_id = 'lead-erase-me'")
    assert row["email"] is None
    assert row["legal_decision"] == "retention-erased"
    audit = Database(dbfile).one(
        "SELECT actor, action FROM audit_logs ORDER BY id DESC LIMIT 1")
    assert audit["action"] == "privacy.erase"
    assert audit["actor"] == "dev-open"


def test_erase_endpoint_unknown_lead_is_404(tmp_path, monkeypatch):
    client, _ = _erase_client(tmp_path, monkeypatch)
    r = client.post("/api/privacy/erase", json={"lead_id": "nope"})
    assert r.status_code == 404


def test_erase_endpoint_requires_lead_id(tmp_path, monkeypatch):
    client, _ = _erase_client(tmp_path, monkeypatch)
    r = client.post("/api/privacy/erase", json={})
    assert r.status_code == 422
