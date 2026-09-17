"""Job state machine.

Legacy pipeline path:
QUEUED -> RUNNING -> (DEGRADED) -> COMPLETED
                    -> PAUSED -> RESUMING -> RUNNING

Agentic research path (docs/plan-agentic-research.md) extends RUNNING with
observable phases and stops at a human review point:
QUEUED -> RUNNING -> DISCOVERING/RESEARCHING/VERIFYING/QUALIFYING (rounds)
       -> READY_FOR_REVIEW -> COMPLETED            (user: APPROVE/REJECT/SAVE)
       -> RUNNING                                   (user: RESEARCH_MORE)
WAITING_FOR_USER  = the agent asked an open question and cannot progress.
WAITING_FOR_CAPACITY = PAUSED (quota/provider exhaustion) — same resource
state the legacy path uses, one name.
CANCELLED is terminal and reachable from any live state — user action only.
FAILED stays reserved for unrecoverable errors.
"""
from .db import Database, utcnow

QUEUED = "QUEUED"
RUNNING = "RUNNING"
DEGRADED = "DEGRADED"
PAUSED = "PAUSED"
RESUMING = "RESUMING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
DISCOVERING = "DISCOVERING"
RESEARCHING = "RESEARCHING"
VERIFYING = "VERIFYING"
QUALIFYING = "QUALIFYING"
WAITING_FOR_USER = "WAITING_FOR_USER"
READY_FOR_REVIEW = "READY_FOR_REVIEW"
CANCELLED = "CANCELLED"

WAITING_FOR_CAPACITY = PAUSED  # alias — capacity exhaustion is a resource state

RESEARCH_PHASES = (DISCOVERING, RESEARCHING, VERIFYING, QUALIFYING)
INTERRUPTED_STATES = (
    RUNNING, RESUMING, DEGRADED, DISCOVERING, RESEARCHING, VERIFYING, QUALIFYING,
)


# research phases interleave freely (the loop re-enters discovery during
# replanning), can hand control back to RUNNING, pause for capacity, ask the
# user, or reach the review gate. COMPLETED is deliberately NOT a phase exit:
# research work always passes through READY_FOR_REVIEW first.
_PHASE_EXITS = ({RUNNING, PAUSED, FAILED, CANCELLED,
                 WAITING_FOR_USER, READY_FOR_REVIEW} | set(RESEARCH_PHASES))

TRANSITIONS = {
    QUEUED: {RUNNING, FAILED, CANCELLED},
    RUNNING: {DEGRADED, PAUSED, COMPLETED, FAILED,
              DISCOVERING, RESEARCHING, VERIFYING, QUALIFYING,
              WAITING_FOR_USER, READY_FOR_REVIEW, CANCELLED},
    DEGRADED: {RUNNING, PAUSED, COMPLETED, FAILED, CANCELLED},  # FAILED added for error recovery
    PAUSED: {RESUMING, FAILED, CANCELLED},
    RESUMING: {RUNNING, PAUSED, FAILED},                        # FAILED added for error recovery
    COMPLETED: set(),
    FAILED: set(),
    DISCOVERING: _PHASE_EXITS,
    RESEARCHING: _PHASE_EXITS,
    VERIFYING: _PHASE_EXITS,
    QUALIFYING: _PHASE_EXITS,
    WAITING_FOR_USER: {RUNNING, CANCELLED, FAILED},
    READY_FOR_REVIEW: {COMPLETED, RUNNING, CANCELLED, FAILED},  # FAILED added for safety
    CANCELLED: set(),
}


class IllegalTransition(Exception):
    pass


class JobManager:
    def __init__(self, db: Database):
        self.db = db

    def create_job(self, icp_id: str, params: dict = None) -> str:
        import json
        import uuid

        job_id = f"job-{uuid.uuid4().hex[:10]}"
        # SQLite parity with the PG adapter's org injection (and with
        # Database.insert_lead): a job row is tenant-scoped at write time so a
        # tenant-filtered status query sees it on both backends. On Postgres the
        # column is already present here, so _inject_org leaves the statement
        # untouched.
        org_id = getattr(self.db, "org_id", None) or "shared"
        self.db.execute(
            "INSERT INTO jobs (job_id, icp_id, state, params, created_at,"
            " updated_at, organization_id) VALUES (?,?,?,?,?,?,?)",
            (job_id, icp_id, QUEUED, json.dumps(params or {}, ensure_ascii=False),
             utcnow(), utcnow(), org_id),
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
        cur = self.db.execute(
            "UPDATE jobs SET state=?, pause_reason=?, updated_at=?"
            " WHERE job_id=? AND state=?",
            (to_state, reason if to_state == PAUSED else None, utcnow(),
             job_id, from_state),
        )
        if getattr(cur, "rowcount", 0) == 0:
            # lost a concurrent race (e.g. the user CANCELLED mid-transition):
            # refuse instead of silently overwriting the newer state
            raise IllegalTransition(
                "race on job %s: %s transition lost (state changed concurrently)"
                % (job_id, to_state))
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

    def recover_interrupted_jobs(self, reason: str = "worker restart: interrupted") -> list[str]:
        """Finds any jobs left in active execution states when the process stopped,
        and transitions them safely to PAUSED so they can be resumed cleanly."""
        placeholders = ",".join("?" for _ in INTERRUPTED_STATES)
        rows = self.db.query(
            f"SELECT job_id, state FROM jobs WHERE state IN ({placeholders})",
            list(INTERRUPTED_STATES),
        )
        recovered = []
        for r in rows:
            job_id = r["job_id"]
            try:
                self.transition(job_id, PAUSED, reason)
                recovered.append(job_id)
            except Exception:
                pass
        return recovered
