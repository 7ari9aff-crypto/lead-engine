"""Postgres-backed job queue on the engine.jobs table.

SKIP LOCKED leasing: a worker claims a job by moving QUEUED -> RUNNING with a
lease; a crashed worker's lease expires and any worker reclaims the job.
Retry policy: fail_job requeues while attempts < max_attempts (exponential
resume_at backoff), else transitions to FAILED.

Inline mode (default when SUPABASE_DB_URL is unset) keeps today's behavior:
jobs execute in-process right after creation. Platform mode enqueues and the
worker process executes them.
"""
import os
from datetime import datetime, timedelta, timezone


def platform_mode() -> bool:
    return bool(os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL"))


def enqueue(db, job_id: str) -> None:
    db.execute("UPDATE jobs SET state='QUEUED', updated_at=? WHERE job_id=?",
               (_now(), job_id))


def lease_next(db, worker_id: str, lease_seconds: int = 600) -> dict | None:
    """Atomically claim the next runnable job. SKIP LOCKED keeps concurrent
    workers from grabbing the same row."""
    row = db.one(
        """
        WITH next_job AS (
          SELECT job_id FROM jobs
          WHERE state IN ('QUEUED', 'RESUMING')
            AND (lease_expires_at IS NULL OR lease_expires_at < now())
            AND (resume_at IS NULL OR resume_at <= now())
          ORDER BY created_at
          FOR UPDATE SKIP LOCKED
          LIMIT 1
        )
        UPDATE jobs j
        SET state='RUNNING', worker_id=?,
            lease_expires_at=now() + make_interval(secs=>?),
            attempts = j.attempts + 1, updated_at=now()
        FROM next_job
        WHERE j.job_id = next_job.job_id
        RETURNING j.job_id, j.icp_id, j.attempts, j.max_attempts
        """,
        (worker_id, lease_seconds),
    )
    return row


def reclaim_expired(db) -> int:
    """Return expired-lease jobs to the queue (crashed worker recovery)."""
    cur = db.execute(
        "UPDATE jobs SET state='QUEUED', worker_id=NULL, lease_expires_at=NULL,"
        " updated_at=? WHERE state='RUNNING' AND lease_expires_at < now()",
        (_now(),))
    return getattr(cur, "rowcount", 0)


def complete(db, job_id: str) -> None:
    db.execute(
        "UPDATE jobs SET state='COMPLETED', worker_id=NULL, lease_expires_at=NULL,"
        " updated_at=? WHERE job_id=?", (_now(), job_id))


def fail(db, job_id: str, reason: str) -> str:
    """Retry with exponential backoff while attempts remain, else FAILED.
    Returns the resulting state."""
    job = db.one("SELECT attempts, max_attempts FROM jobs WHERE job_id=?", (job_id,))
    if not job:
        return "UNKNOWN"
    if (job["attempts"] or 0) < (job["max_attempts"] or 3):
        backoff = min(3600, 60 * (2 ** max(0, job["attempts"] - 1)))
        resume_at = (datetime.now(timezone.utc) + timedelta(seconds=backoff)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        db.execute(
            "UPDATE jobs SET state='QUEUED', worker_id=NULL, lease_expires_at=NULL,"
            " pause_reason=?, resume_at=?, updated_at=? WHERE job_id=?",
            (f"retry: {reason}", resume_at, _now(), job_id))
        return "QUEUED"
    db.execute(
        "UPDATE jobs SET state='FAILED', pause_reason=?, worker_id=NULL,"
        " lease_expires_at=NULL, updated_at=? WHERE job_id=?",
        (reason, _now(), job_id))
    return "FAILED"


def heartbeat(db, job_id: str, worker_id: str, lease_seconds: int = 600) -> None:
    db.execute(
        "UPDATE jobs SET lease_expires_at=now() + make_interval(secs=>?),"
        " updated_at=? WHERE job_id=? AND worker_id=?",
        (lease_seconds, _now(), job_id, worker_id))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
