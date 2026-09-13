"""Research job management — persistent, resumable, budgeted.

A research job is a JOB, not a long HTTP request (directive §32). Everything
needed to (re)start work lives in the database:

- engine.jobs            — the state machine row (extended states)
- engine.research_context — objective, plan, budgets, counters, stop_reason
- engine.research_facts  — everything learned so far (Truth Layer)
- engine.agent_runs/steps — the tool-call trail
- engine.job_events      — every phase transition with reasons

The state must NEVER live in process memory: a worker restart resumes from
these rows (directive §33). Budgets are guardrails, not a workflow order
(§40): the orchestrator checks them before every tool call and stops with a
recorded stop_reason instead of drifting.
"""
import json
from datetime import datetime, timedelta, timezone

from ..db import utcnow
from ..jobs import (
    CANCELLED, COMPLETED, DISCOVERING, FAILED, JobManager, PAUSED, QUALIFYING,
    QUEUED, READY_FOR_REVIEW, RESEARCHING, RUNNING, VERIFYING,
    WAITING_FOR_USER,
)

# Guardrails (directive §40). Overridable per job via budget_json and per
# deployment via settings.yaml research.* — these are the floor defaults.
DEFAULT_BUDGETS = {
    "max_steps": 40,
    "max_tool_calls": 120,
    "max_searches": 60,
    "max_model_calls": 80,
    "max_browse_calls": 30,
    "max_time_minutes": 30,
    "max_candidates": 200,
}

RESEARCH_KIND = "research"


def default_budgets(settings: dict | None = None) -> dict:
    budgets = dict(DEFAULT_BUDGETS)
    cfg = (settings or {}).get("research", {}) or {}
    for key in budgets:
        if key in cfg:
            budgets[key] = cfg[key]
    return budgets


class ResearchJobManager:
    def __init__(self, db, settings: dict | None = None):
        self.db = db
        self.jobs = JobManager(db)
        self.budgets = default_budgets(settings)

    # ------------------------------------------------------------ create
    def create(self, objective: str, *, icp_version_id: str | None = None,
               icp_slug: str | None = None, budgets: dict | None = None,
               parent_job_id: str | None = None) -> str:
        """Create a QUEUED research job + its persistent context row."""
        objective = (objective or "").strip()
        if not objective:
            raise ValueError("objective is required")
        org = getattr(self.db, "org_id", None)
        if getattr(self.db, "dialect", "sqlite") != "sqlite" and not org:
            raise ValueError("research jobs are tenant-scoped: org context required")
        job_id = self.jobs.create_job(icp_slug or "agentic", {
            "kind": RESEARCH_KIND,
            "objective": objective,
            "parent_job_id": parent_job_id,
        })
        merged = {**self.budgets, **(budgets or {})}
        now = utcnow()
        self.db.execute(
            "INSERT INTO research_context (job_id, organization_id, kind,"
            " objective, icp_version_id, plan_json, budget_json, counters_json,"
            " stop_reason, parent_job_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,NULL,?,?,?)",
            (job_id, org, RESEARCH_KIND, objective, icp_version_id,
             None, json.dumps(merged, ensure_ascii=False),
             json.dumps({}, ensure_ascii=False), parent_job_id, now, now))
        return job_id

    # ----------------------------------------------------------- context
    _JSON_COLUMNS = {"plan_json": "plan", "budget_json": "budgets",
                     "counters_json": "counters"}

    def context(self, job_id: str) -> dict | None:
        row = self.db.one("SELECT * FROM research_context WHERE job_id=?", (job_id,))
        if not row:
            return None
        for column, key in self._JSON_COLUMNS.items():
            raw = row.get(column)
            if isinstance(raw, str):
                try:
                    row[key] = json.loads(raw)
                except json.JSONDecodeError:
                    row[key] = None
            else:
                row[key] = raw
        return row

    def is_research(self, job_id: str) -> bool:
        row = self.db.one(
            "SELECT params FROM jobs WHERE job_id=?", (job_id,))
        if not row:
            return False
        try:
            return bool((json.loads(row["params"] or "{}") or {}).get("kind") == RESEARCH_KIND)
        except json.JSONDecodeError:
            return False

    def set_plan(self, job_id: str, plan: dict) -> None:
        self.db.execute(
            "UPDATE research_context SET plan_json=?, updated_at=? WHERE job_id=?",
            (json.dumps(plan, ensure_ascii=False, default=str), utcnow(), job_id))

    # ----------------------------------------------------------- budgets
    def counters(self, job_id: str) -> dict:
        ctx = self.context(job_id)
        return dict(ctx.get("counters") or {}) if ctx else {}

    def bump_counter(self, job_id: str, key: str, n: int = 1) -> int:
        ctx = self.context(job_id)
        if not ctx:
            raise ValueError(f"no research context for {job_id}")
        counters = dict(ctx.get("counters") or {})
        counters[key] = int(counters.get(key) or 0) + n
        self.db.execute(
            "UPDATE research_context SET counters_json=?, updated_at=? WHERE job_id=?",
            (json.dumps(counters, ensure_ascii=False), utcnow(), job_id))
        return counters[key]

    def set_counter(self, job_id: str, key: str, value: int) -> None:
        ctx = self.context(job_id)
        if not ctx:
            raise ValueError(f"no research context for {job_id}")
        counters = dict(ctx.get("counters") or {})
        counters[key] = int(value)
        self.db.execute(
            "UPDATE research_context SET counters_json=?, updated_at=? WHERE job_id=?",
            (json.dumps(counters, ensure_ascii=False), utcnow(), job_id))

    def budget_check(self, job_id: str) -> tuple[bool, str | None, dict]:
        """(ok, exceeded_budget_name, snapshot). One exceeded guardrail is
        enough to stop the loop — the caller records the stop_reason."""
        ctx = self.context(job_id)
        if not ctx:
            return True, None, {}
        budgets = ctx.get("budgets") or {}
        counters = ctx.get("counters") or {}
        snap = {}
        for key, limit in budgets.items():
            if key.startswith("max_") and limit:
                counter_key = {
                    "max_steps": "steps",
                    "max_tool_calls": "tool_calls",
                    "max_searches": "searches",
                    "max_model_calls": "model_calls",
                    "max_browse_calls": "browse_calls",
                    "max_candidates": "candidates",
                }.get(key)
                if counter_key is None:
                    continue
                used = int(counters.get(counter_key) or 0)
                snap[counter_key] = {"used": used, "limit": int(limit)}
                if used >= int(limit):
                    return False, key, snap
        started = ctx.get("created_at")
        minutes = budgets.get("max_time_minutes")
        if started and minutes:
            try:
                elapsed = (datetime.now(timezone.utc) - datetime.strptime(
                    started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                ).total_seconds() / 60
                snap["elapsed_minutes"] = {"used": round(elapsed, 1), "limit": minutes}
                if elapsed >= float(minutes):
                    return False, "max_time_minutes", snap
            except ValueError:
                pass
        return True, None, snap

    # -------------------------------------------------------- transitions
    def set_phase(self, job_id: str, state: str, reason: str | None = None) -> str:
        """Move through research phases (RUNNING -> DISCOVERING -> ...).
        WAITING_FOR_CAPACITY maps to the legacy PAUSED resource state."""
        return self.jobs.transition(job_id, state, reason)

    def pause_for_capacity(self, job_id: str, reason: str, resume_at: str) -> None:
        self.jobs.pause(job_id, reason, resume_at)

    def waiting_for_user(self, job_id: str, question: str) -> str:
        return self.jobs.transition(job_id, WAITING_FOR_USER, question)

    def ready_for_review(self, job_id: str, stop_reason: str,
                         detail: str | None = None) -> str:
        self.db.execute(
            "UPDATE research_context SET stop_reason=?, stop_detail=?, updated_at=?"
            " WHERE job_id=?", (stop_reason, detail, utcnow(), job_id))
        return self.jobs.transition(job_id, READY_FOR_REVIEW, stop_reason)

    def complete(self, job_id: str) -> str:
        return self.jobs.transition(job_id, COMPLETED)

    def cancel(self, job_id: str, by: str | None = None) -> str:
        self.db.execute(
            "UPDATE research_context SET stop_reason='USER_STOPPED', stop_detail=?,"
            " updated_at=? WHERE job_id=?", (f"cancelled by {by or 'user'}",
                                             utcnow(), job_id))
        return self.jobs.transition(job_id, CANCELLED, f"user stop: {by or 'user'}")

    # ---------------------------------------------------------- progress
    def progress(self, job_id: str) -> dict:
        """Everything the chat/UI needs to narrate live progress (§39):
        counters, budgets, truth-layer stats, provider spend, and elapsed."""
        ctx = self.context(job_id) or {}
        job = self.db.one("SELECT state, pause_reason, resume_at, created_at,"
                          " updated_at FROM jobs WHERE job_id=?", (job_id,))
        counters = ctx.get("counters") or {}
        _, _, budget_snap = self.budget_check(job_id)
        stats = {
            "candidates": int(counters.get("candidates") or 0),
            "verified_facts": self._count(
                "SELECT COUNT(*) AS n FROM research_facts WHERE status='VERIFIED'"
                " AND job_id=?", (job_id,)),
            "all_facts": self._count(
                "SELECT COUNT(*) AS n FROM research_facts WHERE job_id=?", (job_id,)),
            "open_conflicts": self._count(
                "SELECT COUNT(*) AS n FROM fact_conflicts WHERE resolution='OPEN'"
                " AND job_id=?", (job_id,)),
            "open_questions": self._count(
                "SELECT COUNT(*) AS n FROM open_questions WHERE job_id=?"
                " AND status='OPEN'", (job_id,)),
            "visited_sources": self._count(
                "SELECT COUNT(*) AS n FROM visited_sources WHERE job_id=?", (job_id,)),
        }
        observability = {
            "providers": self.db.query(
                "SELECT provider, task, COUNT(*) AS calls, COALESCE(SUM(units),0) AS units,"
                " COALESCE(SUM(prompt_tokens),0) AS prompt_tokens,"
                " COALESCE(SUM(completion_tokens),0) AS completion_tokens,"
                " COALESCE(AVG(latency_ms),0) AS avg_latency_ms"
                " FROM usage_ledger WHERE job_id=? GROUP BY provider, task"
                " ORDER BY calls DESC", (job_id,)),
            "steps_recorded": self._count(
                "SELECT COUNT(*) AS n FROM agent_steps WHERE run_id IN"
                " (SELECT run_id FROM agent_runs WHERE input_json LIKE ?)",
                (f'%"{job_id}"%',)),
            "retries_or_errors": self._count(
                "SELECT COUNT(*) AS n FROM usage_ledger WHERE job_id=?"
                " AND status<>'ok'", (job_id,)),
        }
        return {
            "job_id": job_id,
            "state": job["state"] if job else None,
            "pause_reason": job.get("pause_reason") if job else None,
            "objective": ctx.get("objective"),
            "counters": counters,
            "budgets": budget_snap,
            "stop_reason": ctx.get("stop_reason"),
            "stop_detail": ctx.get("stop_detail"),
            "parent_job_id": ctx.get("parent_job_id"),
            "stats": stats,
            "observability": observability,
            "created_at": job.get("created_at") if job else None,
            "updated_at": job.get("updated_at") if job else None,
        }

    def _count(self, sql: str, params) -> int:
        row = self.db.one(sql, params)
        return int(row["n"]) if row else 0
