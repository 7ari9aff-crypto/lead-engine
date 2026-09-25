"""Stale agent-run reaping — the /agents zombie fix.

A serverless request killed mid-run leaves agent_runs.status='RUNNING'
forever: nothing will ever call finish_run on it. The worker tick reaps
runs that have not updated within the stale window to FAILED.
"""
import pytest

from lead_engine.agent_registry import reclaim_stale_runs
from lead_engine.db import Database, utcnow


@pytest.fixture()
def db(tmp_path):
    d = Database(tmp_path / "runs.sqlite3")
    yield d
    d.conn.close()


def _mk_run(db, run_id, status, updated_at):
    db.execute(
        "INSERT INTO agent_runs (run_id, agent_id, version, status,"
        " created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (run_id, "agent-x", "1.0.0", status, "2020-01-01T00:00:00Z", updated_at))


def test_stale_running_run_is_failed(db):
    _mk_run(db, "run-old", "RUNNING", "2020-01-01T00:00:00Z")
    assert reclaim_stale_runs(db) == 1
    row = db.one("SELECT status, error FROM agent_runs WHERE run_id=?",
                 ("run-old",))
    assert row["status"] == "FAILED"
    assert "stale" in row["error"]


def test_fresh_running_run_is_touched(db):
    _mk_run(db, "run-live", "RUNNING", utcnow())
    assert reclaim_stale_runs(db) == 0
    assert db.one("SELECT status FROM agent_runs WHERE run_id=?",
                  ("run-live",))["status"] == "RUNNING"


def test_terminal_runs_are_never_touched(db):
    _mk_run(db, "run-done", "COMPLETED", "2020-01-01T00:00:00Z")
    assert reclaim_stale_runs(db) == 0
    assert db.one("SELECT status FROM agent_runs WHERE run_id=?",
                  ("run-done",))["status"] == "COMPLETED"
