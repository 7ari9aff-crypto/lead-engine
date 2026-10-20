"""Regression tests for the 2026-10-20 audit (work/AUDIT_REPORT.md)."""
import pytest

from lead_engine import queue
from lead_engine.db import open_db
from lead_engine.jobs import JobManager


@pytest.fixture
def db(tmp_path, monkeypatch):
    from lead_engine import db as db_module
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "t.db")
    d = open_db()
    yield d
    d.close()


# ---- C1/C2: research-phase jobs with an expired lease must be reclaimed
@pytest.mark.parametrize("phase", ["DISCOVERING", "RESEARCHING", "VERIFYING", "QUALIFYING"])
def test_reclaim_expired_covers_research_phases(db, phase):
    jm = JobManager(db)
    j = jm.create_job("icp-x")
    queue.lease_next(db, "w1", 600)
    jm.transition(j, phase, "x")
    db.execute("UPDATE jobs SET lease_expires_at='2026-01-01T00:00:00Z' WHERE job_id=?", (j,))
    assert queue.reclaim_expired(db) == 1
    assert jm.current(j) == "QUEUED"


def test_reclaim_ignores_live_lease_in_research_phase(db):
    jm = JobManager(db)
    j = jm.create_job("icp-x")
    queue.lease_next(db, "w1", 600)
    jm.transition(j, "DISCOVERING", "x")
    assert queue.reclaim_expired(db) == 0
    assert jm.current(j) == "DISCOVERING"


# ---- A1: verified user with NO membership must not ride the bridge org
BRIDGE = "11111111-1111-1111-1111-111111111111"


def _make_members_table(db, rows=()):
    """Emulate Postgres' public schema on SQLite so the real query runs."""
    db.conn.execute("ATTACH DATABASE ':memory:' AS public")
    db.conn.execute("CREATE TABLE public.organization_members"
                    " (user_id TEXT, organization_id TEXT, role TEXT, created_at TEXT)")
    for r in rows:
        db.conn.execute("INSERT INTO public.organization_members VALUES (?,?,?,?)", r)


def _req(sub):
    from types import SimpleNamespace
    return SimpleNamespace(state=SimpleNamespace(claims={"sub": sub}))


def test_no_membership_fails_closed_when_membership_table_exists(db, monkeypatch):
    from lead_engine import tenant
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", BRIDGE)
    _make_members_table(db)
    tenant.apply_context(db, _req("stranger"))
    assert db.org_id == "__no_org__"


def test_member_resolves_to_own_org(db, monkeypatch):
    from lead_engine import tenant
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", BRIDGE)
    _make_members_table(db, [("u1", "org-u1", "owner", "2026-01-01")])
    tenant.apply_context(db, _req("u1"))
    assert db.org_id == "org-u1"


def test_bridge_still_used_when_no_membership_table(db, monkeypatch):
    """Ephemeral single-org SQLite deployments keep working (documented design)."""
    from lead_engine import tenant
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", BRIDGE)
    tenant.apply_context(db, _req("anyone"))
    assert db.org_id == BRIDGE


def test_get_db_dependency_matches_tenant_policy(db, monkeypatch):
    from lead_engine.api import app as app_module
    monkeypatch.setenv("LEAD_ENGINE_ORG_ID", BRIDGE)
    monkeypatch.setattr(app_module, "open_db", lambda *a, **k: db)
    _make_members_table(db)
    gen = app_module.get_db(_req("stranger"))
    handle = next(gen)
    assert handle.org_id == "__no_org__"


# ---- E1/E2: provider API keys must never reach error text
SECRET = "AIzaSyFAKEKEY_1234567890abcdef"


def _provider(monkeypatch, name="gemini"):
    from lead_engine.providers import llm
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    cls = next(c for n, c in vars(llm).items()
               if isinstance(c, type) and getattr(c, "name", None) == name)
    return cls({})


def test_connection_error_text_does_not_contain_key(monkeypatch):
    import requests
    from lead_engine.router import ProviderUnavailable
    p = _provider(monkeypatch)

    def boom(self, method, url, **kw):
        raise requests.ConnectionError(f"HTTPConnectionPool: Max retries with url: /m?key={SECRET}")
    monkeypatch.setattr(requests.Session, "request", boom)
    with pytest.raises(ProviderUnavailable) as ei:
        p._http("POST", "https://x.invalid/m", json={})
    assert SECRET not in str(ei.value)


def test_http_error_body_does_not_contain_key(monkeypatch):
    import requests
    from lead_engine.router import ProviderError
    p = _provider(monkeypatch)

    class R:
        status_code = 400
        headers = {}
        text = f"bad request for key {SECRET}"
    monkeypatch.setattr(requests.Session, "request", lambda self, m, u, **kw: R())
    with pytest.raises(ProviderError) as ei:
        p._http("POST", "https://x.invalid/m", json={})
    assert SECRET not in str(ei.value)


def test_gemini_sends_key_in_header_not_url(monkeypatch):
    import requests
    p = _provider(monkeypatch)
    seen = {}

    class R:
        status_code = 200
        headers = {}
        def json(self): return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    def fake(self, method, url, **kw):
        seen["url"], seen["headers"] = url, kw.get("headers") or {}
        return R()
    monkeypatch.setattr(requests.Session, "request", fake)
    p._generate([{"role": "user", "parts": [{"text": "hi"}]}])
    assert SECRET not in seen["url"]
    assert seen["headers"].get("x-goog-api-key") == SECRET


# ---- D2: phone normalisation
@pytest.mark.parametrize("raw", [
    "+966112345678", "00966112345678", "00 966 11 234 5678",
    "0112345678", "011 234 5678", "966112345678",
    "+966١١٢٣٤٥٦٧٨", "٠١١٢٣٤٥٦٧٨",
])
def test_saudi_landline_forms_normalise_identically(raw):
    from lead_engine.pipeline.normalize import normalize_phone
    assert normalize_phone(raw, "SA") == "+966112345678"


@pytest.mark.parametrize("raw", ["0501234567", "+966501234567", "00966501234567", "966501234567"])
def test_saudi_mobile_forms_normalise_identically(raw):
    from lead_engine.pipeline.normalize import normalize_phone
    assert normalize_phone(raw, "SA") == "+966501234567"


def test_normalise_keeps_foreign_numbers_intact():
    from lead_engine.pipeline.normalize import normalize_phone
    assert normalize_phone("+20 100 123 4567", "SA") == "+201001234567"
    assert normalize_phone("0020 100 123 4567", "SA") == "+201001234567"


# ---- D1/D2: dedup
C = dict(city="Riyadh", country="SA")


def _dedup(leads):
    from lead_engine.pipeline.dedup import DedupEngine
    return DedupEngine({}).run(leads)


def test_shared_phone_with_different_domains_not_merged():
    out, _ = _dedup([dict(name="Smile Dental", domain="smile.sa", phone="+966112345678", **C),
                     dict(name="Pearl Dental", domain="pearl.sa", phone="+966112345678", **C)])
    assert len(out) == 2


def test_shared_email_with_different_domains_not_merged():
    out, _ = _dedup([dict(name="A Clinic", domain="a.sa", email="info@group.sa", **C),
                     dict(name="B Clinic", domain="b.sa", email="info@group.sa", **C)])
    assert len(out) == 2


def test_transitive_chain_across_three_domains_not_merged():
    out, _ = _dedup([dict(name="A", domain="a.sa", phone="+966111111111", **C),
                     dict(name="B", domain="b.sa", phone="+966111111111", email="x@y.sa", **C),
                     dict(name="C", domain="c.sa", email="x@y.sa", **C)])
    assert len(out) == 3


def test_same_domain_still_merges():
    out, st = _dedup([dict(name="Smile Dental", domain="smile.sa", **C),
                      dict(name="Smile Dental Clinic", domain="smile.sa", phone="+966112345678", **C)])
    assert len(out) == 1 and st.merged_count == 1


def test_same_phone_one_side_without_domain_merges():
    out, _ = _dedup([dict(name="Smile Dental", domain="smile.sa", **C),
                     dict(name="Smile Dental Riyadh", domain=None, phone="0112345678", **C)])
    out2, _ = _dedup([dict(name="Smile Dental", domain="smile.sa", phone="+966112345678", **C),
                      dict(name="Smile Dental Riyadh", domain=None, phone="0112345678", **C)])
    assert len(out2) == 1


def test_local_and_international_phone_forms_dedupe():
    out, _ = _dedup([dict(name="Alpha", domain=None, phone="0501234567", **C),
                     dict(name="Beta Totally Different", domain=None, phone="+966501234567", **C)])
    assert len(out) == 1


def test_dedup_never_outputs_a_group_spanning_two_domains():
    """Property check: random leads sharing phones/emails/names across domains."""
    import random
    from lead_engine.pipeline.dedup import DedupEngine
    rng = random.Random(7)
    phones = ["+966111111111", "0111111111", "+966122222222", None]
    emails = ["info@g.sa", "x@y.sa", None]
    names = ["Smile Dental", "Smile Dental Clinic", "Pearl", "Al Amal", "عيادة الأمل"]
    for _ in range(200):
        leads = [dict(lead_id=f"L{n}", name=rng.choice(names),
                      domain=rng.choice(["a.sa", "b.sa", "c.sa", None]),
                      phone=rng.choice(phones), email=rng.choice(emails), **C)
                 for n in range(rng.randint(2, 8))]
        out, _ = DedupEngine({}).run(leads)
        for rec in out:
            doms = {x["domain"] for x in leads
                    if x["lead_id"] in rec["source_ids"] and x["domain"]}
            assert len(doms) <= 1


# ---- D3: an INVALID email must never yield an ACCEPTED lead
def _stage(lead):
    from lead_engine.pipeline.orchestrator import decide_stage
    return decide_stage(lead, {"storage_allowed": True, "requires_review": False})


def test_invalid_email_blocks_acceptance():
    assert _stage({"qualification_score": 95, "email": "bad@x.sa", "email_status": "INVALID"}) == "REVIEW"


def test_invalid_email_sets_review_flag_reason():
    lead = {"qualification_score": 95, "email": "bad@x.sa", "email_status": "INVALID"}
    _stage(lead)
    assert lead.get("requires_review") is True


@pytest.mark.parametrize("status", ["DELIVERABLE", "RISKY", "CATCH_ALL", "UNKNOWN", None])
def test_other_email_statuses_do_not_block_acceptance(status):
    assert _stage({"qualification_score": 95, "email": "a@x.sa", "email_status": status}) == "ACCEPTED"


def test_storage_not_allowed_still_rejects():
    from lead_engine.pipeline.orchestrator import decide_stage
    assert decide_stage({"qualification_score": 95}, {"storage_allowed": False, "requires_review": False}) == "REJECTED"


def test_low_score_goes_to_review():
    assert _stage({"qualification_score": 10}) == "REVIEW"
