"""Live Postgres queue test — skipped when SUPABASE_DB_URL is not configured."""
import os
import uuid

import pytest

from lead_engine.config import load_env

load_env()
DSN = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(not DSN, reason="requires SUPABASE_DB_URL")


@pytest.fixture
def db():
    from lead_engine.db import open_db

    db = open_db()
    yield db
    db.conn.close()


@pytest.fixture
def org_id():
    return os.environ.get("LEAD_ENGINE_ORG_ID")


def _mk_job(db, org_id):
    job_id = f"job-queue-test-{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO jobs (job_id, organization_id, icp_id, state, created_at, updated_at)"
        " VALUES (?, ?, 'v0_saudi_dental', 'QUEUED', ?, ?)",
        (job_id, org_id, "2026-09-11T19:00:00Z", "2026-09-11T19:00:00Z"))
    return job_id


def _cleanup(db, job_id):
    db.execute("DELETE FROM job_events WHERE job_id = ?", (job_id,))
    db.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))


def test_queue_lifecycle(db, org_id):
    from lead_engine import queue

    job_id = _mk_job(db, org_id)
    try:
        queue.enqueue(db, job_id)
        leased = queue.lease_next(db, "worker-test")
        assert leased and leased["job_id"] == job_id
        assert leased["attempts"] == 1
        assert db.one("SELECT state FROM jobs WHERE job_id=?", (job_id,))["state"] == "RUNNING"

        queue.heartbeat(db, job_id, "worker-test")

        # fail -> exponential-backoff requeue (attempts 1 < 3)
        assert queue.fail(db, job_id, "simulated") == "QUEUED"

        # backoff holds the job: clear resume_at to simulate the wait
        db.execute("UPDATE jobs SET resume_at = NULL WHERE job_id=?", (job_id,))
        leased2 = queue.lease_next(db, "worker-test")
        assert leased2 and leased2["attempts"] == 2

        queue.complete(db, job_id)
        assert db.one("SELECT state FROM jobs WHERE job_id=?", (job_id,))["state"] == "COMPLETED"
    finally:
        _cleanup(db, job_id)


def test_fail_exhausts_to_failed(db, org_id):
    from lead_engine import queue

    job_id = _mk_job(db, org_id)
    try:
        db.execute("UPDATE jobs SET attempts = 3 WHERE job_id=?", (job_id,))
        assert queue.fail(db, job_id, "no attempts left") == "FAILED"
        assert db.one("SELECT state FROM jobs WHERE job_id=?", (job_id,))["state"] == "FAILED"
    finally:
        _cleanup(db, job_id)
