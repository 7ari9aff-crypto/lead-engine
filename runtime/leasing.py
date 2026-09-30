"""Lease-based job claiming with fencing (ADR-0004).

- claim_next: FOR UPDATE SKIP LOCKED; stamps lease_token (new), bumps
  lease_version, sets lease_expires_at, attempts += 1.
- Every sensitive write is FENCED on (lease_token, lease_version): a stale
  worker's write matches 0 rows and raises LeaseLostError — a zombie can never
  clobber a newer attempt.
- reclaim_expired requeues jobs whose lease lapsed; at-least-once semantics
  mean handlers must be idempotent (effect ledger + claim truth rules).
"""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Json

from contracts.errors import LeaseLostError

ACTIVE_STATES = (
    "PLANNING", "DISCOVERING", "RESEARCHING", "ENRICHING",
    "VERIFYING", "SCORING", "QUALIFYING", "CANCELLING",
)
TERMINAL_STATES = ("READY_FOR_REVIEW", "CANCELLED", "FAILED", "PARTIAL_SUCCESS")


def create_job(db, org_id: str, job_type: str, payload: dict[str, Any],
               queue: str = "default", campaign_id: str | None = None,
               max_attempts: int = 3, priority: int = 100) -> str:
    with db.tx_system() as conn, conn.cursor() as cur:
        row = cur.execute(
            """INSERT INTO runtime.jobs (org_id, campaign_id, job_type, queue, payload,
                                         max_attempts, priority)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (org_id, campaign_id, job_type, queue, Json(payload), max_attempts, priority),
        ).fetchone()
        cur.execute(
            """INSERT INTO runtime.job_events (job_id, org_id, kind, data)
               VALUES (%s, %s, 'created', '{}'::jsonb)""",
            (row["id"], org_id),
        )
        return str(row["id"])


def claim_next(db, queues: list[str], worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
    with db.tx_system() as conn, conn.cursor() as cur:
        row = cur.execute(
            """UPDATE runtime.jobs SET
                 state = 'PLANNING',
                 lease_token = gen_random_uuid(),
                 lease_version = lease_version + 1,
                 lease_expires_at = now() + make_interval(secs => %s),
                 worker_id = %s,
                 attempts = attempts + 1,
                 started_at = COALESCE(started_at, now()),
                 updated_at = now()
               WHERE id = (
                 SELECT id FROM runtime.jobs
                 WHERE queue = ANY(%s) AND state = 'QUEUED'
                   AND attempts < max_attempts
                 ORDER BY priority, created_at
                 LIMIT 1
                 FOR UPDATE SKIP LOCKED
               )
               RETURNING *""",
            (lease_seconds, worker_id, queues),
        ).fetchone()
        return row


def heartbeat(db, job_id: str, lease_token: str, lease_seconds: int) -> bool:
    """Renew the lease. Fenced: a lost lease returns False."""
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE runtime.jobs
               SET lease_expires_at = now() + make_interval(secs => %s), updated_at = now()
               WHERE id = %s AND lease_token::text = %s
                 AND state NOT IN ('READY_FOR_REVIEW','CANCELLED','FAILED')""",
            (lease_seconds, job_id, lease_token),
        )
        return cur.rowcount == 1


def set_phase(db, job_id: str, lease_token: str, lease_version: int,
              state: str, lease_seconds: int = 120) -> None:
    """Phase transition, fenced. Also renews the lease for the next phase."""
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE runtime.jobs
               SET state = %s, updated_at = now(),
                   lease_expires_at = now() + make_interval(secs => %s)
               WHERE id = %s AND lease_token::text = %s AND lease_version = %s""",
            (state, lease_seconds, job_id, lease_token, lease_version),
        )
        if cur.rowcount == 0:
            raise LeaseLostError(f"job {job_id} lease lost during phase {state}")


def save_checkpoint(db, job_id: str, lease_token: str, lease_version: int,
                    checkpoint: dict[str, Any], state: str | None = None,
                    lease_seconds: int = 120) -> None:
    """Persist execution state (architecture §9: nothing important lives only
    in RAM). Fenced; optionally transitions state in the same write."""
    assignments = "checkpoint = %s"
    params: tuple = (Json(checkpoint),)
    if state is not None:
        assignments += ", state = %s"
        params = (*params, state)
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            f"""UPDATE runtime.jobs
                SET {assignments}, updated_at = now(),
                    lease_expires_at = now() + make_interval(secs => %s)
                WHERE id = %s AND lease_token::text = %s AND lease_version = %s""",
            (*params, lease_seconds, job_id, lease_token, lease_version),
        )
        if cur.rowcount == 0:
            raise LeaseLostError(f"job {job_id} lease lost during checkpoint")


def request_cancel(db, org_id: str, job_id: str, cancelled_by: str, reason: str) -> bool:
    """User-facing cancellation request. Not fenced (the job may be running
    or not); the worker turns this into the CANCELLING → CANCELLED machine."""
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE runtime.jobs
               SET cancel_requested_at = now(), cancelled_by = %s,
                   cancellation_reason = %s, updated_at = now()
               WHERE id = %s AND org_id = %s
                 AND state NOT IN ('READY_FOR_REVIEW','CANCELLED','FAILED')""",
            (cancelled_by, reason, job_id, org_id),
        )
        return cur.rowcount == 1


def resume_job(db, org_id: str, job_id: str) -> bool:
    """Requeue a PAUSED/WAITING_FOR_USER job."""
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE runtime.jobs SET state = 'QUEUED', updated_at = now()
               WHERE id = %s AND org_id = %s
                 AND state IN ('PAUSED','WAITING_FOR_USER')""",
            (job_id, org_id),
        )
        return cur.rowcount == 1


def complete(db, job_id: str, lease_token: str, lease_version: int,
             state: str = "READY_FOR_REVIEW") -> None:
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE runtime.jobs
               SET state = %s, finished_at = now(), updated_at = now(),
                   lease_expires_at = NULL, lease_token = NULL
               WHERE id = %s AND lease_token::text = %s AND lease_version = %s""",
            (state, job_id, lease_token, lease_version),
        )
        if cur.rowcount == 0:
            raise LeaseLostError(f"job {job_id} lease lost on completion")


def fail(db, job_id: str, lease_token: str, lease_version: int, error: str) -> str:
    """Fenced failure: requeue for retry while attempts remain, else FAILED."""
    with db.tx_system() as conn, conn.cursor() as cur:
        row = cur.execute(
            """UPDATE runtime.jobs
               SET last_error = %s, updated_at = now(),
                   state = CASE WHEN attempts >= max_attempts
                                THEN 'FAILED' ELSE 'QUEUED' END,
                   finished_at = CASE WHEN attempts >= max_attempts THEN now() END,
                   lease_expires_at = NULL, lease_token = NULL
               WHERE id = %s AND lease_token::text = %s AND lease_version = %s
               RETURNING state""",
            (error[:800], job_id, lease_token, lease_version),
        ).fetchone()
        if row is None:
            raise LeaseLostError(f"job {job_id} lease lost on failure")
        return row["state"]


def reclaim_expired(db, batch: int = 50) -> list[str]:
    """Reaper: requeue jobs whose lease lapsed. Fencing makes this safe — if
    the old worker is alive and writes, it loses (0 rows) and stops.
    Jobs that already burned their attempt budget are FAILED, not requeued:
    a crash loop (OOM, timeout kill) never reaches fail(), so without this
    check the same job would be re-claimed forever, every worker tick."""
    failed: list[str] = []
    requeued: list[str] = []
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE runtime.jobs
               SET state = 'FAILED', finished_at = now(),
                   lease_token = NULL, lease_expires_at = NULL,
                   last_error = 'lease expired after max attempts; not requeued',
                   updated_at = now()
               WHERE id IN (
                 SELECT id FROM runtime.jobs
                 WHERE state = ANY(%s) AND lease_expires_at < now()
                   AND attempts >= max_attempts
                 LIMIT %s
               )
               RETURNING id""",
                (list(ACTIVE_STATES), batch),
        )
        failed = [str(r["id"]) for r in cur.fetchall()]
        remaining = batch - len(failed)
        if remaining > 0:
            cur.execute(
                """UPDATE runtime.jobs
                   SET state = 'QUEUED', lease_token = NULL, lease_expires_at = NULL,
                       last_error = 'lease expired; requeued', updated_at = now()
                   WHERE id IN (
                     SELECT id FROM runtime.jobs
                     WHERE state = ANY(%s) AND lease_expires_at < now()
                     LIMIT %s
                   )
                   RETURNING id""",
                    (list(ACTIVE_STATES), remaining),
            )
            requeued = [str(r["id"]) for r in cur.fetchall()]
    return requeued + failed


def apply_cancellation(db, job_id: str, lease_token: str, lease_version: int) -> bool:
    """Move a cancel-requested job into CANCELLING under its current lease."""
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE runtime.jobs SET state = 'CANCELLING', updated_at = now()
               WHERE id = %s AND lease_token::text = %s AND lease_version = %s
                 AND cancel_requested_at IS NOT NULL
                 AND state NOT IN ('CANCELLING')""",
            (job_id, lease_token, lease_version),
        )
        return cur.rowcount == 1


def finish_cancelled(db, job_id: str, lease_token: str, lease_version: int) -> None:
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE runtime.jobs SET state = 'CANCELLED', finished_at = now(),
                   updated_at = now(), lease_expires_at = NULL, lease_token = NULL
               WHERE id = %s AND lease_token::text = %s AND lease_version = %s""",
            (job_id, lease_token, lease_version),
        )


def get_job(db, org_id: str, job_id: str) -> dict[str, Any] | None:
    with db.tx_system() as conn, conn.cursor() as cur:
        return cur.execute(
            "SELECT * FROM runtime.jobs WHERE id = %s AND org_id = %s",
            (job_id, org_id),
        ).fetchone()


def list_jobs(db, org_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with db.tx_system() as conn, conn.cursor() as cur:
        return list(cur.execute(
            """SELECT id, campaign_id, job_type, queue, state, current_phase, attempts,
                      max_attempts, last_error, created_at, started_at, finished_at
               FROM runtime.jobs WHERE org_id = %s
               ORDER BY created_at DESC LIMIT %s""",
            (org_id, limit),
        ).fetchall())


def active_job_count(db, org_id: str) -> int:
    with db.tx_system() as conn, conn.cursor() as cur:
        row = cur.execute(
            """SELECT count(*) AS n FROM runtime.jobs
               WHERE org_id = %s AND (state = 'QUEUED' OR state = ANY(%s))""",
            (org_id, list(ACTIVE_STATES)),
        ).fetchone()
        return int(row["n"])


def append_job_event(db, job_id: str, org_id: str, kind: str, data: dict[str, Any]) -> None:
    with db.tx_system() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO runtime.job_events (job_id, org_id, kind, data)
               VALUES (%s, %s, %s, %s)""",
            (job_id, org_id, kind, Json(data)),
        )
