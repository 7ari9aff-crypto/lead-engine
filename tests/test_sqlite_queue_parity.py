"""SQLite parity for the queue's lease columns on `jobs`.

queue.py drives jobs.worker_id / lease_expires_at / attempts / max_attempts
on Postgres; the CLI worker and any SQLite deployment must be able to run
the same machinery locally (a worker started against SQLite used to die on
`no such column: worker_id`).
"""
import pytest

from lead_engine.db import Database, utcnow
from lead_engine.jobs import JobManager
from lead_engine import queue


@pytest.fixture()
def db(tmp_path):
    d = Database(tmp_path / "parity.sqlite3")
    yield d
    d.conn.close()


def test_jobs_table_has_lease_columns(db):
    cols = {row["name"] for row in db.conn.execute(
        "PRAGMA table_info(jobs)").fetchall()}
    assert {"worker_id", "lease_expires_at", "attempts", "max_attempts"} <= cols


def test_queue_retry_machinery_runs_on_sqlite(db):
    job_id = JobManager(db).create_job("icp-1")
    queue.enqueue(db, job_id)
    assert queue.fail(db, job_id, "boom") == "QUEUED"
    row = db.one("SELECT state, pause_reason, resume_at, attempts,"
                 " max_attempts FROM jobs WHERE job_id=?", (job_id,))
    assert row["state"] == "QUEUED"
    assert row["pause_reason"] == "retry: boom"
    assert row["resume_at"] is not None
    assert row["attempts"] == 0
    assert row["max_attempts"] == 3

    queue.complete(db, job_id)
    assert db.one("SELECT state FROM jobs WHERE job_id=?",
                  (job_id,))["state"] == "COMPLETED"


def test_queue_lease_machinery_runs_on_sqlite(db):
    job_id = JobManager(db).create_job("icp-1")
    queue.enqueue(db, job_id)

    job = queue.lease_next(db, "w-test", lease_seconds=600)
    assert job and job["job_id"] == job_id

    row = db.one("SELECT state, worker_id, lease_expires_at, attempts"
                 " FROM jobs WHERE job_id=?", (job_id,))
    assert row["state"] == "RUNNING"
    assert row["worker_id"] == "w-test"
    assert row["attempts"] == 1
    assert row["lease_expires_at"] > utcnow()

    queue.heartbeat(db, job_id, "w-test", lease_seconds=600)
    # a live lease must not be reclaimed...
    assert queue.reclaim_expired(db) == 0
    # ...but an expired one returns to the queue
    db.execute("UPDATE jobs SET lease_expires_at='2000-01-01T00:00:00Z'"
               " WHERE job_id=?", (job_id,))
    assert queue.reclaim_expired(db) == 1
    assert db.one("SELECT state FROM jobs WHERE job_id=?",
                  (job_id,))["state"] == "QUEUED"


def test_reclaim_covers_legacy_rows_without_lease(db):
    # legacy inline runs (before queue mode) left RUNNING rows with no lease
    # at all — the expired-lease predicate never matched them, so they zombied
    # forever. Stale ones (no update for a day) must return to the queue.
    job_id = JobManager(db).create_job("icp-1")
    db.execute("UPDATE jobs SET state='RUNNING', updated_at=? WHERE job_id=?",
               ("2020-01-01T00:00:00Z", job_id))
    assert queue.reclaim_expired(db) == 1
    assert db.one("SELECT state FROM jobs WHERE job_id=?",
                  (job_id,))["state"] == "QUEUED"


def test_reclaim_spares_recent_leaseless_runs(db):
    # a fresh inline run owns its RUNNING state until the day-old window
    job_id = JobManager(db).create_job("icp-1")
    db.execute("UPDATE jobs SET state='RUNNING', updated_at=? WHERE job_id=?",
               (utcnow(), job_id))
    assert queue.reclaim_expired(db) == 0
    assert db.one("SELECT state FROM jobs WHERE job_id=?",
                  (job_id,))["state"] == "RUNNING"
