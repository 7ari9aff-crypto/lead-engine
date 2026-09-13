"""R1 — Truth Layer tests: facts, provenance, conflicts, freshness, ICP versions.

The invariants under test (docs/plan-agentic-research.md, Business Truth):
- exactly 5 statuses, nothing in between
- VERIFIED needs 2 INDEPENDENT sources or an explicit verifier
- conflicting fresh values stay visible (never silently overwritten)
- expired knowledge reads back STALE
- org isolation: one tenant never sees another tenant's facts
"""
import pytest

from lead_engine.db import Database
from lead_engine.icp_store import ICPStore
from lead_engine.truth import (
    STATUS_CONFLICTED, STATUS_INFERRED, STATUS_STALE, STATUS_UNVERIFIED,
    STATUS_VERIFIED, FactsStore,
)


@pytest.fixture()
def db(tmp_path):
    return Database(tmp_path / "truth.sqlite3")


@pytest.fixture()
def store(db):
    return FactsStore(db)


def _expire(store, fact_id):
    store.db.execute("UPDATE research_facts SET expires_at='2020-01-01T00:00:00Z'"
                     " WHERE fact_id=?", (fact_id,))


# ---------------------------------------------------------------- recording
def test_single_source_is_unverified(store):
    fact = store.record_fact("company", "org:clinic-a.com", "phone", "+966501234567",
                             source_url="https://clinic-a.com/contact",
                             provider="tavily", query="clinic riyadh")
    assert fact["status"] == STATUS_UNVERIFIED
    assert len(fact["sources"]) == 1
    assert fact["sources"][0]["source_url"] == "https://clinic-a.com/contact"


def test_two_independent_sources_verify(store):
    store.record_fact("company", "org:clinic-a.com", "phone", "+966501234567",
                      source_url="https://clinic-a.com/contact", provider="tavily")
    fact = store.record_fact("company", "org:clinic-a.com", "phone", "+966501234567",
                             source_url="https://directory.sa/listing/1", provider="brave")
    assert fact["status"] == STATUS_VERIFIED
    assert fact["confidence"] >= 0.6


def test_same_domain_does_not_verify(store):
    store.record_fact("company", "org:clinic-a.com", "phone", "+966501234567",
                      source_url="https://clinic-a.com/contact", provider="tavily")
    fact = store.record_fact("company", "org:clinic-a.com", "phone", "+966501234567",
                             source_url="https://clinic-a.com/about", provider="brave")
    assert fact["status"] == STATUS_UNVERIFIED


def test_same_value_freshens_without_new_row(store):
    store.record_fact("company", "org:c.com", "email", "info@c.com",
                      source_url="https://c.com", provider="tavily")
    fact = store.record_fact("company", "org:c.com", "email", "info@c.com",
                             source_url="https://facebook.com/c", provider="brave")
    rows = store.db.query("SELECT COUNT(*) AS n FROM research_facts")
    assert rows[0]["n"] == 1
    assert len(fact["sources"]) == 2


def test_empty_value_rejected(store):
    with pytest.raises(ValueError):
        store.record_fact("company", "org:c.com", "email", "  ")


def test_inferred_fact_has_no_claimed_source(store):
    fact = store.record_fact("company", "org:c.com", "employee_count", "120",
                             quote="estimated from 3 branches", inferred=True)
    assert fact["status"] == STATUS_INFERRED
    assert all(s["source_kind"] == "llm_inference" for s in fact["sources"])


def test_inferred_becomes_unverified_with_source(store):
    store.record_fact("company", "org:c.com", "employee_count", "120", inferred=True)
    fact = store.record_fact("company", "org:c.com", "employee_count", "120",
                             source_url="https://linkedin.com/company/c", provider="apollo")
    assert fact["status"] == STATUS_UNVERIFIED


# ---------------------------------------------------------------- conflicts
def test_conflicting_fresh_values_open_conflict(store):
    a = store.record_fact("company", "org:c.com", "employee_count", "50",
                          source_url="https://a.com", provider="tavily")
    b = store.record_fact("company", "org:c.com", "employee_count", "120",
                          source_url="https://b.com", provider="brave")
    # returned dicts are point-in-time; re-read current state
    a = store.get_fact(a["fact_id"])
    assert a["status"] == STATUS_CONFLICTED
    assert b["status"] == STATUS_CONFLICTED
    conflicts = store.conflicts(subject_id="org:c.com")
    assert len(conflicts) == 1
    assert conflicts[0]["resolution"] == "OPEN"
    assert {conflicts[0]["fact_a"], conflicts[0]["fact_b"]} == {a["fact_id"], b["fact_id"]}


def test_conflict_visible_in_snapshot_with_alternatives(store):
    store.record_fact("company", "org:c.com", "employee_count", "50",
                      source_url="https://a.com", provider="tavily")
    store.record_fact("company", "org:c.com", "employee_count", "120",
                      source_url="https://b.com", provider="brave")
    snap = store.snapshot("company", "org:c.com")
    field = snap["fields"]["employee_count"]
    assert field["status"] == STATUS_CONFLICTED
    assert field["value"] in ("50", "120")
    assert len(field["alternatives"]) == 1
    assert len(snap["conflicts"]) == 1


def test_resolve_conflict_records_winner_and_loser(store):
    a = store.record_fact("company", "org:c.com", "employee_count", "50",
                          source_url="https://a.com", provider="tavily")
    b = store.record_fact("company", "org:c.com", "employee_count", "120",
                          source_url="https://b.com", provider="brave")
    conflict = store.conflicts(subject_id="org:c.com")[0]
    resolved = store.resolve_conflict(conflict["conflict_id"], winner_fact_id=b["fact_id"],
                                      note="apollo data beats directory", by="hosam")
    assert resolved["resolution"] == "RESOLVED_HUMAN"
    assert resolved["resolved_by"] == "hosam"
    assert store.get_fact(b["fact_id"])["status"] == STATUS_VERIFIED
    assert store.get_fact(a["fact_id"])["status"] == STATUS_STALE
    snap = store.snapshot("company", "org:c.com")
    assert snap["fields"]["employee_count"]["status"] == STATUS_VERIFIED
    assert snap["fields"]["employee_count"]["value"] == "120"
    assert snap["conflicts"] == []


def test_expired_value_superseded_without_conflict(store):
    old = store.record_fact("company", "org:c.com", "phone", "+966501111111",
                            source_url="https://old.com", provider="tavily")
    _expire(store, old["fact_id"])
    new = store.record_fact("company", "org:c.com", "phone", "+966502222222",
                            source_url="https://new.com", provider="brave")
    assert store.conflicts(subject_id="org:c.com") == []
    assert store.get_fact(old["fact_id"])["status"] == STATUS_UNVERIFIED  # still, until read
    snap = store.snapshot("company", "org:c.com")
    assert snap["fields"]["phone"]["value"] == "+966502222222"
    assert snap["fields"]["phone"]["status"] == STATUS_UNVERIFIED
    assert "phone" in snap["stale_fields"]


# --------------------------------------------------------------- freshness
def test_expired_fact_reads_back_stale(store):
    fact = store.record_fact("company", "org:c.com", "email", "x@c.com",
                             source_url="https://c.com", provider="tavily")
    _expire(store, fact["fact_id"])
    snap = store.snapshot("company", "org:c.com")
    assert snap["fields"]["email"]["status"] == STATUS_STALE
    # persisted, not just view-level
    assert store.get_fact(fact["fact_id"])["status"] == STATUS_STALE


# ------------------------------------------------------------- verification
def test_verify_fact(store):
    fact = store.record_fact("company", "org:c.com", "email", "x@c.com",
                             source_url="https://c.com", provider="tavily")
    verified = store.verify_fact(fact["fact_id"], outcome="verified",
                                 confidence=0.9, provider="hunter")
    assert verified["status"] == STATUS_VERIFIED
    assert verified["confidence"] == 0.9


def test_refuted_fact_is_no_longer_current(store):
    fact = store.record_fact("company", "org:c.com", "email", "x@c.com",
                             source_url="https://c.com", provider="tavily")
    refuted = store.verify_fact(fact["fact_id"], outcome="refuted",
                                provider="local_smtp", quote="rcpt rejected 550")
    assert refuted["status"] == STATUS_STALE
    assert any("550" in (s["quote"] or "") for s in refuted["sources"])


# ---------------------------------------------------------------- org scope
def test_org_isolation(tmp_path):
    db_a = Database(tmp_path / "a.sqlite3")
    db_a.org_id = "org-a"
    db_b = Database(tmp_path / "b.sqlite3")
    db_b.org_id = "org-b"
    FactsStore(db_a).record_fact("company", "org:c.com", "phone", "+966500000000",
                                 source_url="https://c.com", provider="tavily")
    snap_b = FactsStore(db_b).snapshot("company", "org:c.com")
    assert snap_b["fields"] == {}
    snap_a = FactsStore(db_a).snapshot("company", "org:c.com")
    assert snap_a["fields"]["phone"]["value"] == "+966500000000"


def test_conflicts_scoped_by_org(tmp_path):
    db_a = Database(tmp_path / "a.sqlite3")
    db_a.org_id = "org-a"
    store_a = FactsStore(db_a)
    store_a.record_fact("company", "org:c.com", "phone", "1",
                        source_url="https://a1.com", provider="tavily")
    store_a.record_fact("company", "org:c.com", "phone", "2",
                        source_url="https://a2.com", provider="brave")
    db_b = Database(tmp_path / "b.sqlite3")
    db_b.org_id = "org-b"
    assert FactsStore(db_b).conflicts(subject_id="org:c.com") == []
    assert len(FactsStore(db_a).conflicts(subject_id="org:c.com")) == 1


# ------------------------------------------------- research context support
def test_visited_sources_upsert_by_url(store):
    store.add_visit("job-1", "https://c.com/about", title="About", http_status=200)
    store.add_visit("job-1", "https://c.com/about", title="About (cached)",
                    http_status=200, summary="clinic info")
    rows = store.visited("job-1")
    assert len(rows) == 1
    assert rows[0]["summary"] == "clinic info"


def test_open_questions_lifecycle(store):
    qid = store.add_open_question("job-1", "ما عدد فروع العيادة؟",
                                  subject_id="org:c.com")
    assert len(store.open_questions("job-1")) == 1
    fact = store.record_fact("company", "org:c.com", "branches", "3",
                             source_url="https://c.com", provider="tavily")
    store.answer_open_question(qid, fact["fact_id"])
    assert store.open_questions("job-1") == []
    assert store.open_questions("job-1", status="ANSWERED")[0]["answer_fact_id"] == fact["fact_id"]


def test_facts_for_qualification_shape(store):
    store.record_fact("company", "org:c.com", "city", "Riyadh",
                      source_url="https://c.com", provider="tavily")
    store.record_fact("company", "org:c.com", "phone", "1",
                      source_url="https://a.com", provider="tavily")
    store.record_fact("company", "org:c.com", "phone", "2",
                      source_url="https://b.com", provider="brave")
    flat = store.facts_for_qualification("company", "org:c.com")
    assert flat["values"]["city"] == "Riyadh"
    assert flat["statuses"]["phone"] == STATUS_CONFLICTED
    assert flat["conflicted"] == ["phone"]
    assert "city" not in flat["conflicted"]


# --------------------------------------------------------------- ICP store
def test_icp_versioning_and_activation(db):
    icps = ICPStore(db)
    v1 = icps.create_version("dental-sa", {"industry": "dental", "cities": ["Riyadh"]},
                             source="chat_intent")
    assert v1["status"] == "draft"
    assert icps.active("dental-sa") is None
    icps.activate(v1["icp_version_id"])
    assert icps.active("dental-sa")["version"] == "v1"
    v2 = icps.create_version("dental-sa", {"industry": "dental", "cities": ["Jeddah"]})
    assert v2["version"] == "v2"
    icps.activate(v2["icp_version_id"])
    active = icps.active("dental-sa")
    assert active["icp_version_id"] == v2["icp_version_id"]
    assert active["definition"]["cities"] == ["Jeddah"]
    versions = icps.list_versions("dental-sa")
    statuses = {v["version"]: v["status"] for v in versions}
    assert statuses == {"v1": "retired", "v2": "active"}


def test_icp_duplicate_version_rejected(db):
    icps = ICPStore(db)
    icps.create_version("dental", {"a": 1}, version="v1")
    with pytest.raises(ValueError):
        icps.create_version("dental", {"a": 2}, version="v1")


def test_icp_org_isolation(tmp_path):
    db_a = Database(tmp_path / "a.sqlite3")
    db_a.org_id = "org-a"
    db_b = Database(tmp_path / "b.sqlite3")
    db_b.org_id = "org-b"
    ICPStore(db_a).create_version("dental", {"industry": "dental"})
    assert ICPStore(db_b).list_versions("dental") == []
    assert ICPStore(db_a).list_versions("dental")
