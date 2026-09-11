"""Outreach safety gate: suppression round-trip + policy decisions."""
import pytest

from lead_engine.db import Database
from lead_engine.entitlements import get_limits, check_job_start
from lead_engine.policy import (ALLOW, BLOCK, REVIEW, PolicyGate, Suppression)


@pytest.fixture
def db(tmp_path):
    db = Database(tmp_path / "policy.sqlite3")
    db.execute("CREATE TABLE IF NOT EXISTS organizations (id TEXT PRIMARY KEY, limits TEXT)")
    db.execute("""CREATE TABLE IF NOT EXISTS suppression_entries (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        organization_id TEXT NOT NULL, channel TEXT NOT NULL DEFAULT 'all',
        value TEXT NOT NULL, reason TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'manual',
        created_at TEXT NOT NULL, unique(organization_id, channel, value))""")
    db.execute("""CREATE TABLE IF NOT EXISTS jobs (
        job_id TEXT PRIMARY KEY, organization_id TEXT, icp_id TEXT, state TEXT,
        created_at TEXT, updated_at TEXT)""")
    db.execute("INSERT INTO organizations (id) VALUES ('org-1')")
    yield db
    db.conn.close()


def test_suppression_roundtrip(db):
    Suppression.add(db, "org-1", "email", "a@x.com", "unsubscribed")
    assert Suppression.is_suppressed(db, "org-1", "email", "a@x.com") == (True, "unsubscribed")
    # 'all' channel covers every channel
    Suppression.add(db, "org-1", "all", "b@x.com", "legal")
    ok, reason = Suppression.is_suppressed(db, "org-1", "sms", "b@x.com")
    assert ok and reason == "legal"
    assert not Suppression.is_suppressed(db, "org-1", "email", "clean@x.com")[0]


def test_suppression_remove(db):
    entry = Suppression.add(db, "org-1", "email", "c@x.com", "manual")
    assert Suppression.remove(db, "org-1", entry["id"])
    assert not Suppression.is_suppressed(db, "org-1", "email", "c@x.com")[0]


def test_suppress_bounced_pipeline_hook(db):
    assert Suppression.suppress_bounced(db, "org-1", "dead@x.com", "INVALID")
    assert Suppression.is_suppressed(db, "org-1", "email", "dead@x.com")[0]
    # DELIVERABLE never suppresses
    assert not Suppression.suppress_bounced(db, "org-1", "ok@x.com", "DELIVERABLE")


def test_gate_blocks_suppressed(db):
    Suppression.add(db, "org-1", "email", "x@y.com", "complained")
    d = PolicyGate.evaluate(db, "org-1", "email", "x@y.com")
    assert d.decision == BLOCK and not d.allowed
    assert any("suppressed" in r for r in d.reasons)


def test_gate_allows_clean_with_channel(db):
    d = PolicyGate.evaluate(db, "org-1", "email", "ok@y.com")
    assert d.decision == ALLOW
    assert d.checks["channel"]["allowed"] is True


def test_gate_blocks_disabled_channel(db):
    db.execute("UPDATE organizations SET limits = ? WHERE id = ?", ('{"channels": ["sms"]}', "org-1"))
    d = PolicyGate.evaluate(db, "org-1", "email", "ok@y.com")
    assert d.decision == BLOCK
    assert any("channel not enabled" in r for r in d.reasons)


def test_gate_high_volume_routes_to_review(db):
    d = PolicyGate.evaluate(db, "org-1", "email", "ok@y.com",
                            recent_sends=5000, baseline_per_hour=100)
    assert d.decision == REVIEW
    assert d.checks["risk"]["level"] == "HIGH"


def test_entitlements_defaults_and_limits(db):
    limits = get_limits(db, "org-1")
    assert limits["max_jobs_per_day"] == 10  # default when no limits json
    db.execute("UPDATE organizations SET limits = ? WHERE id = ?", ('{"max_jobs_per_day": 1}', "org-1"))
    assert get_limits(db, "org-1")["max_jobs_per_day"] == 1
    assert check_job_start(db, "org-1")[0] is True  # zero jobs today


def test_missing_org_falls_back_to_defaults(db):
    limits = get_limits(db, "org-missing")
    assert limits["channels"] == ["email"]
