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
    """Return True when jobs should enqueue for a worker instead of running
    inline inside the request.

    Rules (first match wins):
    1. LEAD_ENGINE_QUEUE_MODE=worker  → True  (explicit opt-in)
    2. VERCEL=1 or VERCEL_ENV is set  → True  (vercel.json schedules a cron
       worker; inline execution inside a serverless request is what produced
       the zombie RUNNING runs — the request is killed at maxDuration with no
       lease to reclaim)
    3. LEAD_ENGINE_QUEUE_MODE=inline  → False (explicit opt-out)
    4. Otherwise → False by default (same-process background task; the worker
       CLI must be started separately with `python -m lead_engine worker` —
       set LEAD_ENGINE_QUEUE_MODE=worker to re-enable queue mode)
    """
    # Explicit override always wins
    mode = os.environ.get("LEAD_ENGINE_QUEUE_MODE", "").strip().lower()
    if mode == "worker":
        return True
    if mode == "inline":
        return False
    # Vercel: the scheduled cron worker (api/cron/worker.py) drains the queue
    if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
        return True
    return False


def _is_pg(db) -> bool:
    return getattr(db, "dialect", "sqlite") == "postgres"


def enqueue(db, job_id: str) -> None:
    db.execute("UPDATE jobs SET state='QUEUED', updated_at=? WHERE job_id=?",
               (_now(), job_id))


def lease_next(db, worker_id: str, lease_seconds: int = 600) -> dict | None:
    """Atomically claim the next runnable job. SKIP LOCKED keeps concurrent
    workers from grabbing the same row (Postgres only; SQLite's single-writer
    model needs no lock). The attempts cap keeps a job that repeatedly crashes
    the worker (OOM/kill — it never reaches fail()) from being re-claimed
    forever."""
    attempts_cap = "AND COALESCE(attempts, 0) < COALESCE(max_attempts, 3)"
    if _is_pg(db):
        return db.one(
            f"""
            WITH next_job AS (
              SELECT job_id FROM jobs
              WHERE state IN ('QUEUED', 'RESUMING')
                AND (lease_expires_at IS NULL OR lease_expires_at < now())
                AND (resume_at IS NULL OR resume_at <= now())
                {attempts_cap}
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
    return db.one(
        f"""
        UPDATE jobs
        SET state='RUNNING', worker_id=?,
            lease_expires_at=strftime('%Y-%m-%dT%H:%M:%SZ','now', '+' || ? || ' seconds'),
            attempts = COALESCE(attempts, 0) + 1, updated_at=?
        WHERE job_id = (
          SELECT job_id FROM jobs
          WHERE state IN ('QUEUED', 'RESUMING')
            AND (lease_expires_at IS NULL OR
                 lease_expires_at < strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            AND (resume_at IS NULL OR
                 resume_at <= strftime('%Y-%m-%dT%H:%M:%SZ','now'))
            {attempts_cap}
          ORDER BY created_at
          LIMIT 1
        )
        RETURNING job_id, icp_id, attempts, max_attempts
        """,
        (worker_id, lease_seconds, _now()),
    )


def reclaim_expired(db) -> int:
    """Return expired-lease jobs to the queue (crashed worker recovery).

    Also reaps legacy zombies: RUNNING rows with NO lease are inline runs
    from before queue mode (or a killed inline task); if they have not
    updated for a day they are dead and return to the queue. The day-old
    window spares a live inline run, which owns RUNNING without a lease.
    """
    if _is_pg(db):
        expired = ("(lease_expires_at < now()"
                   " OR (lease_expires_at IS NULL AND"
                   " updated_at < now() - interval '24 hours'))")
    else:
        expired = ("(lease_expires_at < strftime('%Y-%m-%dT%H:%M:%SZ','now')"
                   " OR (lease_expires_at IS NULL AND updated_at <"
                   " strftime('%Y-%m-%dT%H:%M:%SZ','now','-1 day')))")
    # Jobs that already burned their attempt budget are FAILED, not requeued:
    # a crash loop never reaches fail(), so without this branch the same job
    # would be re-claimed forever.
    cur = db.execute(
        "UPDATE jobs SET state='FAILED', worker_id=NULL, lease_expires_at=NULL,"
        " pause_reason='lease expired after max attempts; not requeued',"
        f" updated_at=? WHERE state='RUNNING' AND {expired}"
        " AND COALESCE(attempts, 0) >= COALESCE(max_attempts, 3)",
        (_now(),))
    failed = getattr(cur, "rowcount", 0)
    cur = db.execute(
        "UPDATE jobs SET state='QUEUED', worker_id=NULL, lease_expires_at=NULL,"
        f" updated_at=? WHERE state='RUNNING' AND {expired}",
        (_now(),))
    return failed + getattr(cur, "rowcount", 0)


def expire_stale_paused(db, stale_after_hours: int = 48) -> int:
    """PAUSED with NO resume_at can never resume — nothing ever schedules it
    back (the README's auto-resume promise does not cover this state; two
    production jobs sat in it for 19+ days). Terminal with an audited reason,
    NEVER deleted: the row stays as evidence of the legacy state."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=stale_after_hours)
              ).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = db.query(
        "UPDATE jobs SET state='CANCELLED', pause_reason=?, worker_id=NULL,"
        " lease_expires_at=NULL, updated_at=?"
        " WHERE state='PAUSED' AND resume_at IS NULL AND updated_at < ?"
        " RETURNING job_id",
        ("LEGACY_PAUSED_NO_RESUME_AT: expired by reaper", _now(), cutoff))
    for row in rows:
        db.execute(
            "INSERT INTO job_events (ts, job_id, from_state, to_state, reason)"
            " VALUES (?,?,?,?,?)",
            (_now(), row["job_id"], "PAUSED", "CANCELLED",
             "LEGACY_PAUSED_NO_RESUME_AT"))
    return len(rows)


def complete(db, job_id: str) -> None:
    db.execute(
        "UPDATE jobs SET state='COMPLETED', worker_id=NULL, lease_expires_at=NULL,"
        " updated_at=? WHERE job_id=?", (_now(), job_id))


def release(db, job_id: str) -> None:
    """Clear the lease WITHOUT touching the job state — used when the work
    reached a state owned by someone else (READY_FOR_REVIEW / WAITING_FOR_USER
    for research jobs: the queue is bookkeeping, the human gate owns COMPLETED)."""
    db.execute(
        "UPDATE jobs SET worker_id=NULL, lease_expires_at=NULL, updated_at=?"
        " WHERE job_id=?", (_now(), job_id))


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
    if _is_pg(db):
        db.execute(
            "UPDATE jobs SET lease_expires_at=now() + make_interval(secs=>?),"
            " updated_at=? WHERE job_id=? AND worker_id=?",
            (lease_seconds, _now(), job_id, worker_id))
    else:
        db.execute(
            "UPDATE jobs SET lease_expires_at="
            "strftime('%Y-%m-%dT%H:%M:%SZ','now', '+' || ? || ' seconds'),"
            " updated_at=? WHERE job_id=? AND worker_id=?",
            (lease_seconds, _now(), job_id, worker_id))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
