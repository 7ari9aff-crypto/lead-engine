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


# ---- L10: PAUSED jobs whose resume_at has passed must be woken by the worker tick
def _paused(jm, db, resume_at, org=None):
    j = jm.create_job("icp-x")
    from lead_engine import queue
    queue.lease_next(db, "w1", 600)
    jm.pause(j, "NO_CAPACITY:reasoning", resume_at)
    db.execute("UPDATE jobs SET worker_id=NULL, lease_expires_at=NULL WHERE job_id=?", (j,))
    return j


def test_wake_due_paused_requeues_jobs_past_resume_at(db):
    from lead_engine import queue
    jm = JobManager(db)
    j = _paused(jm, db, "2026-01-01T00:00:00Z")
    assert queue.wake_due_paused(db) == 1
    assert jm.current(j) == "RESUMING"
    # and the very next lease picks it up
    assert queue.lease_next(db, "w2", 600)["job_id"] == j


def test_wake_due_paused_leaves_future_resume_at_alone(db):
    from lead_engine import queue
    jm = JobManager(db)
    j = _paused(jm, db, "2999-01-01T00:00:00Z")
    assert queue.wake_due_paused(db) == 0
    assert jm.current(j) == "PAUSED"


def test_worker_tick_wakes_due_paused_jobs(db):
    from lead_engine.worker import run_worker_tick
    jm = JobManager(db)
    j = _paused(jm, db, "2026-01-01T00:00:00Z")
    result = run_worker_tick(db, "w-tick", settings={})
    assert result["woken"] == 1
    assert jm.current(j) != "PAUSED"


def test_chronic_capacity_failure_ends_in_failed_not_an_endless_loop(db):
    """wake -> lease -> pause(NO_CAPACITY) repeated: the attempts cap must end it."""
    from lead_engine import queue
    jm = JobManager(db)
    j = jm.create_job("icp-x")
    seen = []
    for _ in range(10):
        queue.wake_due_paused(db)
        queue.reclaim_expired(db)
        leased = queue.lease_next(db, "w", 600)
        if not leased:
            break
        seen.append(leased["attempts"])
        # the worker's real behaviour on NO_CAPACITY: queue.fail -> backoff/FAILED
        queue.fail(db, j, "NO_CAPACITY:reasoning")
        db.execute("UPDATE jobs SET resume_at=NULL WHERE job_id=?", (j,))
    assert seen == [1, 2, 3], seen
    assert jm.current(j) == "FAILED"


# ---- L11: Hunter verifier parsing (documented fields: accept_all, webmail,
# disposable, block flags; status enum valid|invalid|accept_all|webmail|disposable|unknown)
def _hunter(data):
    from lead_engine.providers.email import HunterProvider
    p = HunterProvider.__new__(HunterProvider)
    p.name = "hunter"
    p.current_key = lambda: "k"
    p._http = lambda *a, **k: None
    p._json = lambda r: {"data": data}
    return HunterProvider.verify(p, "x@y.com")


@pytest.mark.parametrize("payload", [
    {"result": "valid", "score": 90, "status": "accept_all"},
    {"result": "risky", "score": 70, "accept_all": True},
    {"result": "valid", "score": 90, "accept_all": True, "status": "valid"},
])
def test_hunter_catch_all_is_never_deliverable(payload):
    r = _hunter(payload)
    assert r["status"] == "CATCH_ALL", r
    assert r["confidence"] <= 0.5


def test_hunter_webmail_address_is_not_invalid():
    """A Gmail/Outlook mailbox is a real, deliverable personal address."""
    r = _hunter({"result": "valid", "score": 95, "webmail": True, "status": "webmail"})
    assert r["status"] != "INVALID", r
    assert r["status"] in ("DELIVERABLE", "RISKY")


def test_hunter_disposable_is_still_invalid():
    for payload in ({"result": "valid", "score": 90, "status": "disposable"},
                    {"result": "valid", "score": 90, "disposable": True}):
        assert _hunter(payload)["status"] == "INVALID"


def test_hunter_block_flag_is_not_deliverable():
    """block=true: the server refused verification (greylisting/anti-probe)."""
    r = _hunter({"result": "valid", "score": 90, "block": True})
    assert r["status"] in ("UNKNOWN", "RISKY"), r


def test_hunter_plain_valid_and_invalid_unchanged():
    assert _hunter({"result": "valid", "score": 95, "status": "valid"})["status"] == "DELIVERABLE"
    inv = _hunter({"result": "invalid", "score": 5, "status": "invalid"})
    assert inv["status"] == "INVALID" and inv["confidence"] >= 0.85


# ---- L12: "could not verify" must never be recorded as "proved wrong"
import pytest as _pytest  # noqa: E402


def _email_fact_db(tmp_path, email="dr.salem@clinic.example", job="job-vx"):
    from lead_engine.db import Database
    from lead_engine.truth import FactsStore
    d = Database(tmp_path / "v.db")
    fid = FactsStore(d).record_fact("company", "clinic.example", "email", email,
                                    source_url="https://clinic.example",
                                    provider="tavily", job_id=job)["fact_id"]
    return d, fid


@_pytest.mark.parametrize("status,expected", [
    ("DELIVERABLE", "VERIFIED"),
    ("INVALID", "STALE"),            # positively proved wrong
    ("UNKNOWN", "UNVERIFIED"),       # verifier down / no key / timed out
    ("RISKY", "UNVERIFIED"),
    ("CATCH_ALL", "UNVERIFIED"),
])
def test_verify_tool_outcome_depends_on_proof_not_on_absence_of_proof(tmp_path, status, expected):
    from lead_engine.research import tools

    d, fid = _email_fact_db(tmp_path)

    class V:  # stand-in pipeline returning a fixed verdict
        def __init__(self, router): pass
        def verify(self, value):
            return {"status": status, "confidence": 0.5, "via": "stub",
                    "details": {"reason": "t"}}

    class Mgr:
        def bump_counter(self, *a, **k): pass

    from lead_engine.truth import FactsStore
    ctx = type("C", (), {"store": FactsStore(d), "router": None, "manager": Mgr(),
                         "job_id": "job-vx"})()
    orig = tools.VerificationPipeline
    tools.VerificationPipeline = V
    try:
        out = tools._tool_verify_fact(ctx, {"fact_id": fid})
    finally:
        tools.VerificationPipeline = orig
    assert out["status"] == expected, out


def test_unresolved_emails_are_not_reverified_in_every_slice(tmp_path):
    """An email we could not verify stays UNVERIFIED, so the sweep would pick it up
    again on every slice and pay a provider call each time."""
    from lead_engine.db import Database
    from lead_engine.research import ResearchJobManager
    from lead_engine.research.orchestrator import ResearchOrchestrator
    from lead_engine.truth import FactsStore

    d = Database(tmp_path / "r.db")
    manager = ResearchJobManager(d)
    job_id = manager.create("o")
    FactsStore(d).record_fact("company", "c.example", "email", "a@c.example",
                              source_url="https://c.example", provider="tavily",
                              job_id=job_id)
    calls = []

    class R:
        def route(self, task, payload, **kw):
            calls.append(task)
            return {"provider": "hunter", "status": "UNKNOWN", "confidence": 0.2,
                    "details": {"reason": "no key"}}, {"provider": "hunter"}

    orch = ResearchOrchestrator(d, {}, job_id, router=R())
    orch._verify_emails("run-1")
    orch._verify_emails("run-2")      # next slice / retry
    assert calls.count("email_verify") == 1, calls


# ---- L13: retention sweep must report rows it really erased
def _lead(db, lead_id, created, retention_days=30, marked=None):
    import json
    db.execute(
        "INSERT INTO leads (lead_id, name, email, phone, raw, created_at, updated_at,"
        " legal_decision) VALUES (?,?,?,?,?,?,?,?)",
        (lead_id, "Clinic", "a@b.com", "+966500000000",
         json.dumps({"pipeline": {"retention_days": retention_days}}),
         created, created, marked))


def test_retain_expired_counts_only_rows_actually_erased(db):
    from lead_engine import privacy
    _lead(db, "old-1", "2020-01-01T00:00:00Z")
    _lead(db, "fresh", utcnow())
    assert privacy.retain_expired(db) == 1


def test_retain_expired_is_idempotent_and_does_not_recount(db):
    from lead_engine import privacy
    _lead(db, "old-1", "2020-01-01T00:00:00Z")
    assert privacy.retain_expired(db) == 1
    assert privacy.retain_expired(db) == 0
    row = db.one("SELECT email, phone, legal_decision FROM leads WHERE lead_id='old-1'")
    assert row["email"] is None and row["phone"] is None
    assert row["legal_decision"] == "retention-erased"


def test_erase_lead_on_already_erased_lead_reports_no_new_erasure(db):
    from lead_engine import privacy
    _lead(db, "x", "2020-01-01T00:00:00Z", marked="retention-erased")
    assert privacy._anonymize(db, ["x"], "again") == 0


# ---- OPS1: the backup verifier must catch a bad restore, not just pass a good one
def test_backup_compare_flags_missing_and_short_tables():
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location(
        "backup_verify", pathlib.Path(__file__).parent.parent / "scripts" / "backup_verify.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src = {"engine.leads": 121, "engine.jobs": 38, "runtime.jobs": 14}
    assert mod.compare(src, dict(src)) == []
    bad = mod.compare(src, {"engine.leads": 120, "runtime.jobs": 14})
    assert any("engine.leads" in p and "120" in p for p in bad)
    assert any("MISSING" in p and "engine.jobs" in p for p in bad)
    assert mod.compare({"a.b": 0}, {"a.b": 0}) == []      # empty tables are fine
