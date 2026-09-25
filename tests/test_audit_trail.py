"""Read path over the server-side audit trail: AuditTrailStore + GET /api/audit.

The table (engine.audit_logs / the SQLite mirror in lead_engine/db.py SCHEMA) is
written by Database.audit, PgDatabase.audit and codeops.audit; these tests pin
the first reader: tenant-scoped, filtered, one SELECT per page, identical
envelope on both dialects (payload/timestamps parsed in Python, not SQL).
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lead_engine.activity import AuditTrailStore, get_router
from lead_engine.activity.api import get_db as router_get_db
from lead_engine.activity.store import _canonical_ts, _window_bound
from lead_engine.db import Database
from tests.test_bootstrap_idempotence import CountingDb


@pytest.fixture
def db_file(tmp_path):
    return tmp_path / "audit.sqlite3"


@pytest.fixture
def db(db_file):
    # audit_logs is part of the core SCHEMA (db.py) — no ensure_schema needed.
    d = Database(db_file)
    yield d
    d.conn.close()


def _write(db, actor, action, entity_type=None, entity_id=None,
           payload=None, org="org-a", raw_ts=None):
    """Insert one audit row through the REAL write path (Database.audit)."""
    db.org_id = org
    if raw_ts is None:
        db.audit(actor, action, entity_type, entity_id, payload)
        return
    db.execute(
        "INSERT INTO audit_logs (organization_id, actor, action, entity_type,"
        " entity_id, payload_json, created_at) VALUES (?,?,?,?,?,?,?)",
        (org, actor, action, entity_type, entity_id,
         json.dumps(payload or {}, ensure_ascii=False), raw_ts))


# ------------------------------------------------------------------ store

def test_constructing_audit_store_issues_no_statements(db):
    counting = CountingDb(db)
    AuditTrailStore(counting)
    assert counting.count == 0, "request-path constructor must stay free (LAT-01)"


def test_one_page_is_one_statement_even_with_every_filter(db):
    """The N+1 guard: 40 rows, every filter active — still exactly one SELECT."""
    for i in range(40):
        _write(db, "sara@example.test", "lead.approve", "lead", f"lead:{i}",
               {"i": i})
    counting = CountingDb(db)
    counting.org_id = "org-a"
    store = AuditTrailStore(counting)
    before = counting.count
    page = store.list(limit=20, offset=0, actor="sara@example.test",
                      action="lead.approve", entity_type="lead",
                      entity_id="lead:7",
                      created_from="2020-01-01", created_to="2038-01-01")
    assert counting.count - before == 1, (
        f"paged read cost {counting.count - before} statements; must be 1")
    assert len(page["entries"]) == 1  # entity_id narrows to one row
    assert "LIMIT ?" in counting.sql[-1] and "OFFSET ?" in counting.sql[-1]


def test_list_is_newest_first_with_stable_keyset_cursor(db):
    for i in range(5):
        _write(db, "op", f"act.{i}", "lead", "l1")
    store = AuditTrailStore(db)
    store.db.org_id = "org-a"
    page1 = store.list(limit=2)["entries"]
    assert [e["action"] for e in page1] == ["act.4", "act.3"]  # newest first
    cursor = page1[-1]["id"]
    page2 = store.list(limit=2, before_id=cursor)["entries"]
    assert [e["action"] for e in page2] == ["act.2", "act.1"]
    assert {e["id"] for e in page1} & {e["id"] for e in page2} == set()
    assert store.list(limit=2, offset=1)["entries"][0]["action"] == "act.3"


def test_filters_on_actor_action_and_entity(db):
    _write(db, "sara", "lead.approve", "lead", "lead:1")
    _write(db, "omar", "lead.reject", "lead", "lead:2")
    _write(db, "sara", "code_patch.applied", "approval", "ap:9")
    store = AuditTrailStore(db)
    store.db.org_id = "org-a"
    assert [e["action"] for e in store.list(actor="sara")["entries"]] == [
        "code_patch.applied", "lead.approve"]
    assert [e["id"] for e in store.list(action="lead.reject")["entries"]] == [
        e["id"] for e in store.list(entity_type="lead", entity_id="lead:2")["entries"]]
    prov = store.list(entity_type="lead", entity_id="lead:1")["entries"]
    assert len(prov) == 1 and prov[0]["actor"] == "sara"
    assert store.list(action="missing.action")["entries"] == []


def test_time_window_filters_across_both_writer_timestamp_formats(db):
    # db.utcnow() style (Z, second precision) and codeops style (+00:00, micros)
    _write(db, "op", "a.old", raw_ts="2026-09-24T10:00:00Z")
    _write(db, "op", "a.midnight_micro", raw_ts="2026-09-25T00:00:01.500000+00:00")
    _write(db, "op", "a.noon", raw_ts="2026-09-25T12:00:00Z")
    _write(db, "op", "a.new", raw_ts="2026-09-26T10:00:00Z")
    store = AuditTrailStore(db)
    store.db.org_id = "org-a"
    got = lambda **kw: [e["action"] for e in store.list(**kw)["entries"]]  # noqa: E731
    assert got(created_from="2026-09-25", created_to="2026-09-25") == [
        "a.noon", "a.midnight_micro"]          # date-only until = whole day
    assert got(created_from="2026-09-25T12:00:00Z") == ["a.new", "a.noon"]
    assert got(created_to="2026-09-24T23:59:59Z") == ["a.old"]
    assert got(created_from="2020-01-01", created_to="2030-01-01") == [
        "a.new", "a.noon", "a.midnight_micro", "a.old"]


def test_invalid_window_bound_raises_valueerror(db):
    store = AuditTrailStore(db)
    store.db.org_id = "org-a"
    with pytest.raises(ValueError):
        store.list(created_from="yesterday-ish")
    with pytest.raises(ValueError):
        store.list(created_to="2026-13-45")


def test_window_bound_normalisation():
    assert _window_bound("2026-09-25") == "2026-09-25T00:00:00Z"
    assert _window_bound("2026-09-25", end=True) == "2026-09-25T23:59:59Z"
    assert _window_bound("2026-09-25T08:30:00+02:00") == "2026-09-25T06:30:00Z"
    assert _window_bound("") is None and _window_bound(None) is None
    assert _canonical_ts(None) is None
    assert _canonical_ts("garbage-not-a-date") == "garbage-not-a-date"


# ------------------------------------------------- tenant visibility rules

def _seed_every_visibility_class(db):
    _write(db, "op", "mine.1", org="org-a")
    _write(db, "op", "mine.2", org="org-a")
    _write(db, "op", "theirs.1", org="org-b")
    _write(db, "op", "unattributed.1", org=None)
    _write(db, "op", "unattributed.2", org="")
    _write(db, "op", "failclosed.1", org="__no_org__")


def test_tenant_sees_only_its_own_rows(db):
    """Stricter than the activity feed: no NULL/sentinel legacy visibility —
    audit payloads name entity ids that may belong to other tenants."""
    _seed_every_visibility_class(db)
    store = AuditTrailStore(db)
    store.db.org_id = "org-a"
    actions = [e["action"] for e in store.list()["entries"]]
    assert sorted(actions) == ["mine.1", "mine.2"]
    assert store.list()["scope"] == "tenant"
    # cross-check: org-b caller sees its own row and nothing else
    store.db.org_id = "org-b"
    assert [e["action"] for e in store.list()["entries"]] == ["theirs.1"]


def test_sentinel_caller_fails_closed_with_zero_statements(db):
    _seed_every_visibility_class(db)
    counting = CountingDb(db)
    counting.org_id = "__no_org__"
    page = AuditTrailStore(counting).list()
    assert page == {"entries": [], "scope": "none"}
    assert counting.count == 0, "fail-closed must not even hit the database"


def test_machine_context_sees_only_unattributable_rows(db):
    """A worker/n8n/dev caller with no tenant sees rows no tenant owns —
    including fail-closed sentinel writes — and never another tenant's."""
    _seed_every_visibility_class(db)
    for org in (None, "", "__whatever__"):
        store = AuditTrailStore(db)
        store.db.org_id = org
        if org == "__whatever__":  # any '__'-prefixed context fails closed
            assert store.list()["scope"] == "none"
            continue
        actions = sorted(e["action"] for e in store.list()["entries"])
        assert actions == ["failclosed.1", "unattributed.1", "unattributed.2"]
        assert store.list()["scope"] == "platform"


# ------------------------------------------------------ payload/timestamps

def test_payload_parsed_and_unicode_preserved(db):
    _write(db, "op", "lead.approve", "lead", "l1",
           {"note": "موافق بعد المراجعة", "nested": {"ok": True}})
    store = AuditTrailStore(db)
    store.db.org_id = "org-a"
    entry = store.list()["entries"][0]
    assert entry["payload"] == {"note": "موافق بعد المراجعة", "nested": {"ok": True}}
    assert isinstance(entry["payload_json"], str)  # raw row stays reconstructable
    assert entry["created_at"].endswith("Z") and "T" in entry["created_at"]


def test_corrupt_payload_degrades_to_empty_dict(db):
    _write(db, "op", "x", raw_ts="2026-09-25T10:00:00Z")
    db.execute("UPDATE audit_logs SET payload_json = 'not { json'")
    store = AuditTrailStore(db)
    store.db.org_id = "org-a"
    assert store.list()["entries"][0]["payload"] == {}


class _FakePg:
    """Mimics PgDatabase.query output: jsonb/timestamptz already stringified
    by _normalize — the store must issue exactly one dialect-neutral SELECT."""

    dialect = "postgres"
    org_id = "org-a"

    def __init__(self, rows):
        self._rows = rows
        self.sql = []

    def query(self, sql, params=()):
        self.sql.append(sql)
        return [dict(r) for r in self._rows]


def test_postgres_shaped_rows_parse_identically():
    pg = _FakePg([{
        "id": 7, "organization_id": "org-a", "actor": "sara",
        "action": "lead.approve", "entity_type": "lead", "entity_id": "l1",
        "payload_json": json.dumps({"note": "ok"}),  # db_pg stringifies jsonb
        "created_at": "2026-09-25T09:00:00Z",        # db_pg canonicalises too
    }])
    page = AuditTrailStore(pg).list()
    assert len(pg.sql) == 1
    entry = page["entries"][0]
    assert entry["payload"] == {"note": "ok"} and entry["created_at"].endswith("Z")


def test_store_survives_unmapped_jsonb_and_datetime_objects():
    """Defensive: if a future adapter returns native dict/datetime objects
    instead of strings, reads still normalise."""
    from datetime import datetime, timezone

    pg = _FakePg([{
        "id": 8, "organization_id": "org-a", "actor": "omar",
        "action": "lead.reject", "entity_type": "lead", "entity_id": "l2",
        "payload_json": {"reason": "غير مطابق"},
        "created_at": datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc),
    }])
    entry = AuditTrailStore(pg).list()["entries"][0]
    assert entry["payload"] == {"reason": "غير مطابق"}
    assert entry["created_at"] == "2026-09-25T09:00:00Z"


# ------------------------------------------------------------------ router

def _client(db_file, org="org-a"):
    """Mount ONLY the activity router (as app.py:2006 does), with tenant
    resolution overridden to a fixture database — same as test_activity.py."""
    def override_get_db():
        d = Database(db_file)
        d.org_id = org
        try:
            yield d
        finally:
            d.conn.close()

    app = FastAPI()
    app.include_router(get_router())
    app.dependency_overrides[router_get_db] = override_get_db
    return TestClient(app)


def test_router_empty_envelope(db_file):
    client = _client(db_file, org=None)
    r = client.get("/api/audit")
    assert r.status_code == 200
    assert r.json() == {"entries": [], "count": 0, "scope": "platform",
                        "limit": 50, "offset": 0, "next_before_id": None}


def test_router_tenant_scoped_read_and_entity_provenance(db_file):
    seed = Database(db_file)
    _write(seed, "sara@x.test", "lead.approve", "lead", "job1:dental.sa",
           {"note": "تمت الموافقة"}, org="org-a")
    _write(seed, "omar@x.test", "lead.reject", "lead", "job1:other.sa",
           org="org-b")
    seed.conn.close()

    client = _client(db_file)
    body = client.get("/api/audit").json()["entries"]
    assert [e["actor"] for e in body] == ["sara@x.test"]  # org-b row invisible

    r = client.get("/api/audit", params={"entity_type": "lead",
                                         "entity_id": "job1:dental.sa"})
    entry = r.json()["entries"][0]
    assert entry["action"] == "lead.approve"
    assert entry["payload"] == {"note": "تمت الموافقة"}
    assert r.json()["scope"] == "tenant"

    # the other tenant's entity: empty, not a 500 and not leaked
    r = client.get("/api/audit", params={"entity_id": "job1:other.sa"})
    assert r.json() == {"entries": [], "count": 0, "scope": "tenant",
                        "limit": 50, "offset": 0, "next_before_id": None}


def test_router_clamps_limit_and_walks_cursor(db_file):
    seed = Database(db_file)
    for i in range(6):
        _write(seed, "op", f"act.{i}", "lead", "l1", org="org-a")
    seed.conn.close()
    client = _client(db_file)
    r = client.get("/api/audit", params={"limit": 500})
    assert r.json()["limit"] == 200  # clamped, not rejected (activity convention)

    page1 = client.get("/api/audit", params={"limit": 2}).json()
    assert page1["count"] == 2 and page1["next_before_id"] == page1["entries"][1]["id"]
    page2 = client.get("/api/audit", params={
        "limit": 2, "before_id": page1["next_before_id"]}).json()
    assert {e["id"] for e in page1["entries"]} & {e["id"] for e in page2["entries"]} == set()
    assert [e["action"] for e in page2["entries"]] == ["act.3", "act.2"]


def test_router_rejects_bad_inputs(db_file):
    client = _client(db_file)
    assert client.get("/api/audit", params={"from": "last-tuesday"}).status_code == 400
    assert client.get("/api/audit", params={"to": "2026-02-30T00:00:00Z"}).status_code == 400
    assert client.get("/api/audit", params={"before_id": -3}).status_code == 400
    assert client.get("/api/audit", params={"limit": "abc"}).status_code == 422


def test_router_sentinel_context_sees_nothing(db_file):
    seed = Database(db_file)
    _write(seed, "op", "mine", "lead", "l1", org="org-a")
    _write(seed, "op", "theirs", "lead", "l2", org="org-b")
    seed.conn.close()
    client = _client(db_file, org="__no_org__")
    r = client.get("/api/audit")
    assert r.status_code == 200
    body = r.json()
    assert body["entries"] == [] and body["scope"] == "none"
