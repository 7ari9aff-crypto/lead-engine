"""Logic-bug regressions found in the 2026-10-20 partner review."""
import pytest

from lead_engine import entitlements
from lead_engine.db import open_db, utcnow
from lead_engine.jobs import JobManager
from lead_engine.ratelimit import RateLimiter


@pytest.fixture
def db(tmp_path, monkeypatch):
    from lead_engine import db as db_module
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "t.db")
    d = open_db()
    yield d
    d.close()


# ---- L1: failed/cancelled jobs must not burn the customer's daily job quota
def test_failed_and_cancelled_jobs_do_not_consume_daily_quota(db, monkeypatch):
    monkeypatch.setattr(entitlements, "get_limits",
                        lambda _db, _org: {"max_jobs_per_day": 3})
    jm = JobManager(db)
    for state in ("FAILED", "CANCELLED", "FAILED"):
        j = jm.create_job("icp-x")
        db.execute("UPDATE jobs SET state=?, organization_id='org1' WHERE job_id=?", (state, j))
    ok, reason = entitlements.check_job_start(db, "org1")
    assert ok, f"3 failed/cancelled jobs wrongly exhausted a 3/day quota: {reason}"


def test_real_jobs_still_count_toward_quota(db, monkeypatch):
    monkeypatch.setattr(entitlements, "get_limits",
                        lambda _db, _org: {"max_jobs_per_day": 2})
    jm = JobManager(db)
    for state in ("COMPLETED", "RUNNING"):
        j = jm.create_job("icp-x")
        db.execute("UPDATE jobs SET state=?, organization_id='org1' WHERE job_id=?", (state, j))
    ok, _ = entitlements.check_job_start(db, "org1")
    assert not ok


# ---- L2: behind Vercel's proxy every user shares the proxy IP -> one bucket
def _scope(ip, xff=None, path="/api/leads"):
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return {"type": "http", "method": "GET", "path": path,
            "client": (ip, 1234), "headers": headers}


def test_rate_limit_buckets_by_real_client_ip_behind_proxy(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    rl = RateLimiter(rps=0.0001, burst=2)
    # user A exhausts their own burst
    assert rl.allow(_scope("10.0.0.1", "1.1.1.1"))[0]
    assert rl.allow(_scope("10.0.0.1", "1.1.1.1"))[0]
    assert not rl.allow(_scope("10.0.0.1", "1.1.1.1"))[0]
    # user B, same proxy IP but different real client, must NOT be throttled
    assert rl.allow(_scope("10.0.0.1", "2.2.2.2"))[0], \
        "different real clients behind one proxy share a single bucket"


def test_xff_is_ignored_when_not_behind_trusted_proxy(monkeypatch):
    """A spoofed XFF must not let a direct client dodge the limiter."""
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    rl = RateLimiter(rps=0.0001, burst=2)
    assert rl.allow(_scope("9.9.9.9", "1.1.1.1"))[0]
    assert rl.allow(_scope("9.9.9.9", "1.1.1.2"))[0]
    assert not rl.allow(_scope("9.9.9.9", "1.1.1.3"))[0], "spoofed XFF bypassed limiter"


# ---- L3: an INVALID email must never score higher than having no email
def test_invalid_email_does_not_boost_score():
    from lead_engine.pipeline.filters import Scorer
    s = Scorer({})
    base = {"qualification_score": 70, "source_urls": ["a", "b", "c"]}
    no_email = s.score(dict(base))
    invalid = s.score(dict(base, email="x@y.com", email_status="INVALID"))
    deliverable = s.score(dict(base, email="x@y.com", email_status="DELIVERABLE"))
    assert invalid <= no_email, f"INVALID email ({invalid}) outscored no email ({no_email})"
    assert deliverable > no_email  # a verified email must still help


def test_invalid_email_does_not_count_as_contact_method_with_phone():
    from lead_engine.pipeline.filters import Scorer
    s = Scorer({})
    base = {"qualification_score": 70, "source_urls": ["a"], "phone": "+966500000000"}
    phone_only = s.score(dict(base))
    phone_bad_email = s.score(dict(base, email="x@y.com", email_status="INVALID"))
    assert phone_bad_email <= phone_only


# ---- L4: Scorer must not mutate the shared settings dict
def test_scorer_does_not_mutate_settings():
    from lead_engine.pipeline.filters import Scorer
    cfg = {"scoring": {"weights": {"qualification": 0.9}}}
    Scorer(cfg)
    assert cfg["scoring"]["weights"] == {"qualification": 0.9}


def test_scorer_partial_weights_are_normalised_to_one():
    from lead_engine.pipeline.filters import Scorer
    s = Scorer({"scoring": {"weights": {"qualification": 0.9}}})
    assert abs(sum(s.weights.values()) - 1.0) < 1e-9
    top = s.score({"qualification_score": 100, "source_urls": ["a", "b", "c"],
                   "email": "a@b.com", "phone": "1", "email_status": "DELIVERABLE"})
    assert top <= 100.0


# ---- L5: legal gate is default-deny: no provenance != approved source
_POL = {"data_types": {"company_public_data": {"retention_days": 30}},
        "source_types": {"search_api": {"approved": True}},
        "purposes": {"lead_generation": {}}}


def test_lead_without_any_source_requires_review():
    from lead_engine.pipeline.legal_gate import LegalGate
    v = LegalGate(_POL).evaluate({"name": "x"})
    assert v["requires_review"] is True
    assert v["source_policy"] == "needs_review"
    assert v["decision"] == "REVIEW"


def test_lead_with_approved_source_still_accepted():
    from lead_engine.pipeline.legal_gate import LegalGate
    v = LegalGate(_POL).evaluate({"name": "x", "sources": ["search_api"]})
    assert v["decision"] == "ACCEPTED" and v["source_policy"] == "approved"


# ---- L6: the query budget must be spread across ALL requested cities
def test_query_budget_is_shared_across_cities():
    from collections import Counter
    from lead_engine.pipeline.icp import build_adhoc_icp, build_plan
    icp = build_adhoc_icp(["Riyadh", "Jeddah", "Dammam"], "dental", max_queries=4)
    per_city = Counter(q["city"] for q in build_plan(icp)["queries"])
    assert set(per_city) == {"Riyadh", "Jeddah", "Dammam"}, \
        f"cities starved by the budget: {dict(per_city)}"
    assert sum(per_city.values()) == 4


def test_budget_larger_than_total_keeps_every_query():
    from lead_engine.pipeline.icp import build_adhoc_icp, build_plan
    icp = build_adhoc_icp(["Riyadh", "Jeddah"], "dental", max_queries=999)
    plan = build_plan(icp)
    assert len(plan["queries"]) == 2 * (len(icp["keywords_en"]) + len(icp["keywords_ar"]))


def test_single_city_order_is_unchanged():
    from lead_engine.pipeline.icp import build_adhoc_icp, build_plan
    icp = build_adhoc_icp(["Riyadh"], "dental", max_queries=3)
    qs = build_plan(icp)["queries"]
    assert [q["lang"] for q in qs] == ["en", "en", "ar"]


# ---- L7: recovered jobs must be resumable, never an eternal PAUSED zombie
def test_recovered_job_gets_a_resume_at(db):
    from lead_engine import queue
    jm = JobManager(db)
    j = jm.create_job("icp-x")
    queue.lease_next(db, "w1", 600)
    assert jm.recover_interrupted_jobs() == [j]
    row = db.one("SELECT state, resume_at FROM jobs WHERE job_id=?", (j,))
    assert row["state"] == "PAUSED"
    assert row["resume_at"], "PAUSED without resume_at can never resume (expire_stale_paused reaps it)"


def test_recover_skips_jobs_with_a_live_lease(db):
    """A job a live worker still holds (unexpired lease) must not be paused."""
    from lead_engine import queue
    jm = JobManager(db)
    j = jm.create_job("icp-x")
    queue.lease_next(db, "w1", 600)             # lease valid for 10 min
    assert jm.recover_interrupted_jobs(respect_leases=True) == []
    assert jm.current(j) == "RUNNING"


def test_recover_still_pauses_expired_lease_jobs(db):
    from lead_engine import queue
    jm = JobManager(db)
    j = jm.create_job("icp-x")
    queue.lease_next(db, "w1", 600)
    db.execute("UPDATE jobs SET lease_expires_at='2026-01-01T00:00:00Z' WHERE job_id=?", (j,))
    assert jm.recover_interrupted_jobs(respect_leases=True) == [j]


# ---- L8: fail() must survive a NULL attempts counter
def test_fail_handles_null_attempts(db):
    from lead_engine import queue
    jm = JobManager(db)
    j = jm.create_job("icp-x")
    db.execute("UPDATE jobs SET state='RUNNING', attempts=NULL WHERE job_id=?", (j,))
    assert queue.fail(db, j, "boom") == "QUEUED"


# ---- L9: v6 pool must disable server-side prepared statements (pgbouncer
# transaction mode reuses backends -> DuplicatePreparedStatement "_pg3_1")
def test_v6_pool_disables_prepared_statements(monkeypatch):
    captured = {}

    class _FakePool:
        def __init__(self, *a, **kw):
            captured.update(kw)
        def wait(self, *a, **k): pass

    from infrastructure.postgres import pool as poolmod
    monkeypatch.setattr(poolmod, "ConnectionPool", _FakePool)
    try:
        poolmod.Database("postgresql://u:p@h:6543/db")
    except Exception:
        pass
    assert captured.get("kwargs", {}).get("prepare_threshold", "missing") is None, captured
