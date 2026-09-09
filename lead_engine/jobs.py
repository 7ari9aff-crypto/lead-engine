"""Job state machine.

QUEUED -> RUNNING -> (DEGRADED) -> COMPLETED
                   -> PAUSED -> RESUMING -> RUNNING

PAUSED means "resource state" (no LLM/search provider available) — the
scheduler retries later. FAILED is reserved for unrecoverable errors:
corrupt database, invalid job, broken configuration.
"""
from .db import Database, utcnow

QUEUED = "QUEUED"
RUNNING = "RUNNING"
DEGRADED = "DEGRADED"
PAUSED = "PAUSED"
RESUMING = "RESUMING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

TRANSITIONS = {
    QUEUED: {RUNNING, FAILED},          # invalid job config
    RUNNING: {DEGRADED, PAUSED, COMPLETED, FAILED},
    DEGRADED: {RUNNING, PAUSED, COMPLETED},
    PAUSED: {RESUMING, FAILED},         # unrecoverable config only
    RESUMING: {RUNNING, PAUSED},
    COMPLETED: set(),
    FAILED: set(),
}


class IllegalTransition(Exception):
    pass


class JobManager:
    def __init__(self, db: Database):
        self.db = db

    def create_job(self, icp_id: str, params: dict = None) -> str:
        import uuid

        job_id = f"job-{uuid.uuid4().hex[:10]}"
        self.db.execute(
            "INSERT INTO jobs (job_id, icp_id, state, params, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (job_id, icp_id, QUEUED, str(params or {}), utcnow(), utcnow()),
        )
        return job_id

    def current(self, job_id: str) -> str:
        row = self.db.one("SELECT state FROM jobs WHERE job_id=?", (job_id,))
        if not row:
            raise ValueError(f"invalid job: {job_id}")
        return row["state"]

    def transition(self, job_id: str, to_state: str, reason: str = None):
        from_state = self.current(job_id)
        if to_state not in TRANSITIONS.get(from_state, set()):
            raise IllegalTransition(f"{from_state} -> {to_state} is not allowed")
        self.db.execute(
            "UPDATE jobs SET state=?, pause_reason=?, updated_at=? WHERE job_id=?",
            (to_state, reason if to_state == PAUSED else None, utcnow(), job_id),
        )
        self.db.execute(
            "INSERT INTO job_events (ts, job_id, from_state, to_state, reason) VALUES (?,?,?,?,?)",
            (utcnow(), job_id, from_state, to_state, reason),
        )
        return to_state

    def pause(self, job_id: str, reason: str, resume_at: str):
        self.transition(job_id, PAUSED, reason)
        self.db.execute("UPDATE jobs SET resume_at=? WHERE job_id=?", (resume_at, job_id))

    def mark_failed(self, job_id: str, reason: str):
        self.transition(job_id, FAILED, reason)

    def resume(self, job_id: str):
        if self.current(job_id) != PAUSED:
            raise IllegalTransition("only PAUSED jobs can resume")
        self.transition(job_id, RESUMING, "scheduler retry")

    def jobs_due_for_resume(self):
        return self.db.query(
            "SELECT job_id, pause_reason, resume_at FROM jobs WHERE state=? AND resume_at <= ?",
            (PAUSED, utcnow()),
        )

    def events(self, job_id: str):
        return self.db.query(
            "SELECT * FROM job_events WHERE job_id=? ORDER BY id", (job_id,)
        )
