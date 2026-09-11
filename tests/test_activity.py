"""Activity feed: store round-trip + filter + FastAPI router."""
import json

import pytest
from fastapi.testclient import TestClient

from lead_engine.activity import ActivityStore, get_router
from lead_engine.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "act.sqlite3")


@pytest.fixture
def store(db):
    return ActivityStore(db)


def test_record_round_trip(store):
    event = store.record("job.started", {"job_id": "abc", "city": "الرياض"},
                         correlation_id="corr-1")
    assert event["id"] > 0
    assert event["kind"] == "job.started"
    assert event["correlation_id"] == "corr-1"
    assert event["payload"] == {"job_id": "abc", "city": "الرياض"}
    assert "T" in event["ts"]  # ISO 8601 with time component


def test_record_without_correlation(store):
    event = store.record("agent.run", {"run_id": "r-1"})
    assert event["correlation_id"] is None
    assert event["payload"] == {"run_id": "r-1"}


def test_list_newest_first(store):
    a = store.record("job.started", {"n": 1})
    b = store.record("job.completed", {"n": 2})
    c = store.record("agent.run", {"n": 3})
    events = store.list()
    assert [e["id"] for e in events] == [c["id"], b["id"], a["id"]]


def test_list_kind_filter(store):
    store.record("job.started", {"n": 1})
    store.record("agent.run", {"n": 2})
    store.record("job.completed", {"n": 3})
    store.record("approval.requested", {"n": 4})

    jobs = store.list(kind="job.started")
    assert len(jobs) == 1
    assert jobs[0]["kind"] == "job.started"
    assert jobs[0]["payload"] == {"n": 1}

    approvals = store.list(kind="approval.requested")
    assert len(approvals) == 1
    assert approvals[0]["kind"] == "approval.requested"

    # Filter with no matches
    assert store.list(kind="missing.kind") == []


def test_list_respects_limit(store):
    for i in range(10):
        store.record("tick", {"i": i})
    events = store.list(limit=3)
    assert len(events) == 3
    # newest first
    assert events[0]["payload"]["i"] == 9
    assert events[1]["payload"]["i"] == 8
    assert events[2]["payload"]["i"] == 7


def test_payload_with_nested_data(store):
    payload = {
        "candidates": [1, 2, 3],
        "nested": {"a": "b", "arr": [True, None]},
        "unicode": "مرحبا",
    }
    event = store.record("agent.step", payload, correlation_id="xyz")
    assert event["payload"] == payload

    listed = store.list()
    assert listed[0]["payload"] == payload


def test_router_list_and_record(tmp_path):
    """Smoke-test the FastAPI router end-to-end with a real DB path."""
    # We override the router's get_db dependency so it points at tmp_path.
    db_file = tmp_path / "router.sqlite3"
    db = Database(db_file)
    db.conn.close()  # reopen fresh below

    from lead_engine.activity.api import get_db as router_get_db
    from fastapi import FastAPI

    def override_get_db():
        d = Database(db_file)
        try:
            yield d
        finally:
            d.conn.close()

    app = FastAPI()
    app.include_router(get_router())
    app.dependency_overrides[router_get_db] = override_get_db
    client = TestClient(app)

    # Empty
    r = client.get("/api/activity")
    assert r.status_code == 200
    assert r.json() == {"events": []}

    # Record one event
    r = client.post("/api/activity", json={
        "kind": "job.started",
        "payload": {"job_id": "j1", "city": "جدة"},
        "correlation_id": "c-1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["event"]["kind"] == "job.started"
    assert body["event"]["payload"] == {"job_id": "j1", "city": "جدة"}
    assert body["event"]["correlation_id"] == "c-1"

    # List with kind filter
    r = client.post("/api/activity", json={
        "kind": "agent.run",
        "payload": {"run_id": "r1"},
    })
    assert r.status_code == 200

    r = client.get("/api/activity", params={"kind": "job.started"})
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["kind"] == "job.started"
    assert events[0]["payload"]["city"] == "جدة"

    # Limit clamp — values above 200 are clamped to 200, not rejected
    r = client.get("/api/activity", params={"limit": 500})
    assert r.status_code == 200
    assert "events" in r.json()


def test_router_post_without_kind_rejected(tmp_path):
    db_file = tmp_path / "bad.sqlite3"
    from lead_engine.activity.api import get_db as router_get_db
    from fastapi import FastAPI

    def override_get_db():
        d = Database(db_file)
        try:
            yield d
        finally:
            d.conn.close()

    app = FastAPI()
    app.include_router(get_router())
    app.dependency_overrides[router_get_db] = override_get_db
    client = TestClient(app)

    r = client.post("/api/activity", json={"payload": {"x": 1}})
    assert r.status_code == 422
